'''
Python module for the dedicated Mopidy Pummeluff threads.
'''

__all__ = (
    'TagReader',
)

import sys
import os
from threading import Thread
from time import time
from logging import getLogger

import RPi.GPIO as GPIO
from pirc522 import RFID

from mopidy_pummeluff.registry import REGISTRY
from mopidy_pummeluff.tags.base import Tag
from mopidy_pummeluff.sound import play_sound

from evdev import InputDevice, ecodes, list_devices
from select import select

LOGGER = getLogger(__name__)

# Important: run, as root, the following command
#   usermod -a -G input
def get_devices():
    return [InputDevice(fn) for fn in list_devices()]

class Reader:
    #reader = None

    def __init__(self):
        #self.reader = self
        path = os.path.dirname(os.path.realpath(__file__))
        self.keys = "X^1234567890XXXXqwertzuiopXXXXasdfghjklXXXXXyxcvbnmXXXXXXXXXXXXXXXXXXXXXXX"
        #if not os.path.isfile(path + '/deviceName.txt'):
        #    sys.exit('Please run RegisterDevice.py first')
        #else:
        #with open(path + '/deviceName.txt', 'r') as f:
        #deviceName = f.read()
        deviceName = 'HXGCoLtd Keyboard'
        devices = get_devices()
        LOGGER.info("looking among " + str(list_devices()))
        for device in devices:
            if device.name == deviceName:
                self.dev = device
                break
        try:
            self.dev
        except:
            LOGGER.error("no device found: " + str(devices))
            sys.exit('Could not find the device %s\n. Make sure is connected' % deviceName)

    def readCard(self):
        stri = ''
        key = ''
        while key != 'KEY_ENTER':
            r, w, x = select([self.dev], [], [])
            for event in self.dev.read():
                if event.type == 1 and event.value == 1:
                    stri += self.keys[event.code]
                    # print( keys[ event.code ] )
                    key = ecodes.KEY[event.code]
        return stri[:-1]

class ReadError(Exception):
    '''
    Exception which is thrown when an RFID read error occurs.
    '''


class TagReader(Thread):
    '''
    Thread which reads RFID tags from the RFID reader.

    Because the RFID reader algorithm is reacting to an IRQ (interrupt), it is
    blocking as long as no tag is touched, even when Mopidy is exiting. Thus,
    we're running the thread as daemon thread, which means it's exiting at the
    same moment as the main thread (aka Mopidy core) is exiting.
    '''
    daemon = True
    latest = None

    def __init__(self, core, stop_event):
        '''
        Class constructor.

        :param mopidy.core.Core core: The mopidy core instance
        :param threading.Event stop_event: The stop event
        '''
        super().__init__()
        self.core       = core
        self.stop_event = stop_event
        #self.rfid      = RFID()
        self.rfid       = Reader()
        LOGGER.info("Initialized tag reader " + str(stop_event))

    def run(self):
        '''
        Run RFID reading loop.
        '''
        rfid      = self.rfid
        prev_time = time()
        prev_uid  = ''

        LOGGER.info("start loop")

        while not self.stop_event.is_set():
            #rfid.wait_for_tag()
            LOGGER.info("waiting for new tag")
            uid = rfid.readCard()
            LOGGER.info("read " + str(uid))

            try:
                now = time()
                #uid = self.read_uid()

                if now - prev_time > 1 or uid != prev_uid:
                    LOGGER.info('Tag %s read', uid)
                    self.handle_uid(uid)

                prev_time = now
                prev_uid  = uid

            except ReadError:
                pass

        GPIO.cleanup()  # pylint: disable=no-member

    def read_uid(self):
        '''
        Return the UID from the tag.

        :return: The hex UID
        :rtype: string
        '''
        rfid = self.rfid

        error, data = rfid.request()  # pylint: disable=unused-variable
        if error:
            raise ReadError('Could not read tag')

        error, uid_chunks = rfid.anticoll()
        if error:
            raise ReadError('Could not read UID')

        uid = '{0[0]:02X}{0[1]:02X}{0[2]:02X}{0[3]:02X}'.format(uid_chunks)  # pylint: disable=invalid-format-index
        return uid

    def handle_uid(self, uid):
        '''
        Handle the scanned tag / retreived UID.

        :param str uid: The UID
        '''
        try:
            tag = REGISTRY[str(uid)]
            LOGGER.info('Triggering action of registered tag')
            play_sound('success.wav')
            tag(self.core)

        except KeyError:
            LOGGER.info('Tag is not registered, thus doing nothing')
            play_sound('fail.wav')
            tag = Tag(uid=uid)

        tag.scanned      = time()
        TagReader.latest = tag
