#!/usr/bin/env python3

import subprocess
import sys
import os
import time
import signal

from subprocess import call

############
# Settings #
############
# For when you don't have headphones in and you want custom volume balance
speaker_balance = 0
# For when YOU DO have headphones in and you want custom volume balance
# (broken debalanced headphones and whatnot)
headphones_balance = 0
# This helps the subwoofer get the correct left/right stereo in so it sounds in center
subwoofer_balance = -75  # Default: -75
# This is extra volume for the subwoofer, independent of what stereo balance it gets as input
extra_volume = 9  # Default: 9;
pulseaudio_detect_intervals = 5  # Default: 5. No. of seconds between pulseaudio detects.

dev = "/dev/snd/hwC1D0"

sudo = '/usr/bin/sudo'
hda_verb = '/usr/bin/hda-verb'

#############
# Functions #
#############

# Global variables
headphones_in = False
speakers_set = False
headphones_set = False
curr_volume = 0
pactl = None

dev_id = 0

# Subwoofer part
################

def enable_subwoofer():
    call([sudo, hda_verb, dev, "0x17", "SET_POWER", "0x0"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    call([sudo, hda_verb, dev, "0x1a", "SET_POWER", "0x0"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    call([sudo, hda_verb, dev, "0x17", "0x300", "0xb000"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    call([sudo, hda_verb, dev, "0x17", "0x707", "0x40"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    call([sudo, hda_verb, dev, "0x1a", "0x707", "0x25"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def disable_subwoofer():
    call([sudo, hda_verb, dev, "0x1a", "0x707", "0x20"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def set_subwoofer_volume(volumes):
    valL = 0xa000 + int(volumes[0])
    valR = 0x9000 + int(volumes[1])
    call([sudo, hda_verb, dev, "0x03", "0x300", hex(valL)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    call([sudo, hda_verb, dev, "0x03", "0x300", hex(valR)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    print("Subwoofer volumes set. Left: " + str(volumes[0]) + ". Right: " + str(volumes[1]) + ".")


def calculate_subwoofer_volume(spk_vol, balance):
    balL = 100
    balR = 100
    if balance < 0:
        balL = 100
        balR = balR + balance
    else:
        balL = balL - balance
        balR = 100

    valL = 87 * spk_vol * balL / 100 / 100 + extra_volume
    valR = 87 * spk_vol * balR / 100 / 100 + extra_volume

    vals = calibrate87([valL, valR])

    return vals


def set_subwoofer():
    vol = get_biggest_volume()
    subVols = calculate_subwoofer_volume(vol, subwoofer_balance)
    set_subwoofer_volume(subVols)


# Speaker part
##############

def calculate_speaker_balance(spk_vol, balance):
    # vol = get_biggest_volume()

    balL = 100
    balR = 100
    if balance < 0:
        balL = 100
        balR = balR + balance
    else:
        balL = balL - balance
        balR = 100

    valL = spk_vol * balL / 100
    valR = spk_vol * balR / 100

    return [valL, valR]


def set_speaker_volumes(volumes):
    volumes = calibrate100(volumes)
    call(["amixer", "-D", "pulse", "set", "Master", str(volumes[0]) + "%," + str(volumes[1]) + "%"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    print("Speaker volumes set. Left: " + str(volumes[0]) + ". Right: " + str(volumes[1]))


def set_speakers():
    global speakers_set
    global headphones_set

    if speakers_set:
        return
    else:
        speakers_set = True
        headphones_set = False

    vol = get_biggest_volume()
    spkVols = calculate_speaker_balance(vol, speaker_balance)
    set_speaker_volumes(spkVols)


def get_biggest_volume():
    volumes = get_volumes()

    if len(volumes) == 1:
        return volumes[0]
    if volumes[0] > volumes[1]:
        return volumes[0]
    else:
        return volumes[1]


def get_volumes():
    amixer = subprocess.Popen(["amixer", "-D", "pulse", "get", "Master"], stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE)
    output = []
    for line in iter(amixer.stdout.readline, ''):
        if line == b'':
            break
        if b'%' in line:
            # noinspection PyTypeChecker
            vol = line.split(b'[')[1].split(b'%]')[0]
            output.append(int(vol))

    return output


# Headphones part
#################

def set_headphones():
    global headphones_set
    global speakers_set

    if headphones_set:
        return
    else:
        headphones_set = True
        speakers_set = False

    vol = get_biggest_volume()
    spkVols = calculate_speaker_balance(vol, headphones_balance)
    set_speaker_volumes(spkVols)


def headphones_in_query():
    global headphones_in

    amixer = subprocess.Popen(["amixer", "-c", str(dev_id), "cget", "numid=22"], stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE)
    i = 0
    count = False
    for l in iter(amixer.stdout.readline, ''):
        if l == b'':
            break
        if b"numid=22" in l:
            count = True
        if count:
            i = i + 1
        if i == 3:
            if b"values=off" in l:
                headphones_in = False
            elif b"values=on" in l:
                headphones_in = True
            break

    amixer.terminate()


def check_headphones():
    headphones_in_query()
    if headphones_in:
        # print("Headphones in.")
        disable_subwoofer()
        set_headphones()
    else:
        # print("Headphones out.")
        enable_subwoofer()
        set_speakers()


# Additional functions
######################

def calibrate(volumes, limit):
    if volumes[0] > limit:
        volumes[0] = limit
    elif volumes[0] < 0:
        volumes[0] = 0

    if volumes[1] > limit:
        volumes[1] = limit
    elif volumes[1] < 0:
        volumes[1] = 0

    return [volumes[0], volumes[1]]


def calibrate100(volumes):
    return calibrate(volumes, 100)


def calibrate87(volumes):
    return calibrate(volumes, 87)


def check_volume():
    global curr_volume
    new_volume = get_biggest_volume()

    if curr_volume != new_volume:
        curr_volume = new_volume
        print("Volume change detected: ", curr_volume)

        if not headphones_in:
            set_subwoofer()


# Signal handlers #
###################

def on_exit(*_):
    global pactl
    if pactl is not None:
        pactl.terminate()
    disable_subwoofer()
    exit(0)


def on_suspend(*_):
    print("Disable subwoofer on suspend.")
    disable_subwoofer()


def on_resume(*_):
    print("Enable subwoofer on resume.")
    check_headphones()
    set_subwoofer()


# PulseAudio #
##############

def get_sink_no_and_dev_id():
    """
    Get sink number of Intel HDA device
    """
    # The output should be in English
    pactl_env = os.environ.copy()
    pactl_env['LANG'] = 'en_US'

    p = subprocess.Popen(["pactl", "list", "sinks"], stdout=subprocess.PIPE, env=pactl_env)
    last_sink_no = -1
    card = b''
    driver_name = b''
    profile_name = b''
    for line in iter(p.stdout.readline, ''):
        if line == b'':
            break
        if line.startswith(b"Sink "):
            last_sink_no = line.strip().split(b'#')[1]
            card = b''
            driver_name = b''
            profile_name = b''
        elif b'alsa.card = "' in line:
            card = line.split(b'"')[1]
        elif b'alsa.driver_name = "' in line:
            driver_name = line.split(b'"')[1]
        elif b'device.profile.name = "' in line:
            profile_name = line.split(b'"')[1]

        if profile_name == b"analog-stereo" and driver_name == b"snd_hda_intel" and card:
            return last_sink_no, card

    return -1


########
# Main #
########

def main():
    global pactl, dev_id

    sink_no, dev_id = get_sink_no_and_dev_id()
    if not sink_no or not dev_id:
        print("Device not found!")
        exit(1)

    # Handle signals
    signal.signal(signal.SIGTERM, on_exit)
    signal.signal(signal.SIGUSR1, on_suspend)
    signal.signal(signal.SIGUSR2, on_resume)

    pulseaudio_detected = False
    while not pulseaudio_detected:
        pgrep = subprocess.Popen(["pgrep", "-u", str(os.getuid()), "pulseaudio"], stdout=subprocess.PIPE)
        for line in iter(pgrep.stdout.readline, ''):
            if line == b'':
                break
            if line.strip():
                print("Pulseaudio detected")
                pulseaudio_detected = True
            else:
                time.sleep(pulseaudio_detect_intervals)
        if pgrep is not None:
            pgrep.terminate()

    headphones_in_query()
    if not headphones_in:
        enable_subwoofer()
        set_subwoofer()
        set_speakers()

    # Make it english
    pactl_env = os.environ.copy()
    pactl_env['LANG'] = 'en_US'
    pactl = subprocess.Popen(["pactl", "subscribe"], stdout=subprocess.PIPE, env=pactl_env)
    for event in iter(pactl.stdout.readline, ''):
        if event == b'':
            break
        if b"Event 'change' on sink #" + sink_no in event:
            check_headphones()
            check_volume()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        on_exit()
