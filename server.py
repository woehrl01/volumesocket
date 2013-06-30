###############################################################################
##
##  Copyright 2013, Lukas Woehrl
##
##  Licensed under the Apache License, Version 2.0 (the "License");
##  you may not use this file except in compliance with the License.
##  You may obtain a copy of the License at
##
##      http://www.apache.org/licenses/LICENSE-2.0
##
##  Unless required by applicable law or agreed to in writing, software
##  distributed under the License is distributed on an "AS IS" BASIS,
##  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
##  See the License for the specific language governing permissions and
##  limitations under the License.
##
###############################################################################


import sys
import numpy
import pyaudio
import math
import getopt

from twisted.internet import reactor
from twisted.python import log
from twisted.web.server import Site
from twisted.web.static import File

from autobahn.websocket import WebSocketServerFactory, WebSocketServerProtocol, listenWS

DEFAULT_DEBUG = False
DEFAULT_INTERVAL = 0.250
DEFAULT_DEVICE_NO = 2
DEFAULT_PORT = 9000


def usage():
   print "\n== VolumeSocket =="
   print "This application broadcasts the current ambient volume via websocket."
   print "The volume is recorded via microphone."
   print "\nUsage:"
   print "  -h, --help"
   print "\tShow this help message"
   print "\n  -d=[%(n)d], --device=[%(n)d]" % {'n': DEFAULT_DEVICE_NO}
   print "\tIndex of the input device (default: %d)" % DEFAULT_DEVICE_NO
   print "\n  --debug"
   print "\tEnable debug output"
   print "\n  -i=[%(n)d], --interval=[%(n)d]" % {'n': (DEFAULT_INTERVAL*1000)}
   print "\tDefines the interval between each message in milliseconds (default: %d)" % (DEFAULT_INTERVAL*1000)
   print "\n  -p%(n)d], --port=[%(n)d]" % {'n': DEFAULT_PORT}
   print "\tDefines the port the websockt is running on (default: %d)" % DEFAULT_PORT
   print ""


def calcLoudness(chunk):
   '''
   This method copyright: https://code.google.com/p/pygalaxy/ (LGPL)
   Calculate and return volume of input samples

   Input chunk should be a numpy array of samples for analysis, as
   returned by sound card.  Sound card should be in 16-bit mono mode.
   Return value is measured in dB, will be from 0dB (maximum
   loudness) down to -80dB (no sound).  Typical very loud sound will
   be -1dB, typical silence is -36dB.

   '''
   data = numpy.array(chunk, dtype=float) / 32768.0
   ms = math.sqrt(numpy.sum(data ** 2.0) / len(data))
   if ms < 10e-8: ms = 10e-8
   return 10.0 * math.log(ms, 10.0)


class BroadcastServerProtocol(WebSocketServerProtocol):

   def onOpen(self):
      self.factory.register(self)

   def onMessage(self, msg, binary):
      """ Ignore incomming messages"""
      pass

   def connectionLost(self, reason):
      WebSocketServerProtocol.connectionLost(self, reason)
      self.factory.unregister(self)


class BroadcastServerFactory(WebSocketServerFactory):
   """
   Simple broadcast server broadcasting any message it receives to all
   currently connected clients.
   """

   def __init__(self, url, debug = False, debugCodePaths = False, interval = 0.250, device = 2):
      WebSocketServerFactory.__init__(self, url, debug = debug, debugCodePaths = debugCodePaths)
      self.clients = []
      self.debug = debug
      self.interval = interval
      #prepare audio input
      pyaud = pyaudio.PyAudio()
      self.stream = pyaud.open(
                  format = pyaudio.paInt16,
                  channels = 1,
                  rate = 44100,
                  input_device_index = device,
                  input = True)
      self.tick()

   def tick(self):
      rawsamps = self.stream.read(1024)
      samps = numpy.fromstring(rawsamps, dtype=numpy.int16)
      loudness = calcLoudness(samps)
      loudness *= -1 #make positive to safe space on sending 
      self.broadcast("%.2f" % loudness)
      reactor.callLater(self.interval, self.tick)

   def register(self, client):
      if not client in self.clients:
         if self.debug:
            print "registered client " + client.peerstr
         self.clients.append(client)

   def unregister(self, client):
      if client in self.clients:
         if self.debug:
            print "unregistered client " + client.peerstr
         self.clients.remove(client)

   def broadcast(self, msg):
      if self.debug:
         print "broadcasting volume level '%s' .." % msg
      for c in self.clients:
         c.sendMessage(msg)
         if self.debug:
            print "volume level sent to " + c.peerstr

def main():    
   debug = DEFAULT_DEBUG
   interval = DEFAULT_INTERVAL
   device = DEFAULT_DEVICE_NO
   port = DEFAULT_PORT

   try:
      opts, args = getopt.getopt(sys.argv[1:], "hi:d:p:", ["help", "interval=", "debug", "device=", "port="])
   except getopt.GetoptError:
      usage()
      sys.exit(2)

   for opt, arg in opts:
      if opt in ("-h", "--help"):
         usage()
         sys.exit()
      elif opt in ("-d", "--device"):
         device = int(arg)
      elif opt in ("--debug"):
         log.startLogging(sys.stdout)
         debug = True
      elif opt in ("-i", "--interval"):
         interval = float(arg) / 1000.0
      elif opt in ("-p", "--port"):
         port = int(arg)

   print "Configuration:"
   print "  Debug: %r" % debug
   print "  Interval: %d ms" % (interval * 1000)
   print "  Port: %d" % port
   print "  Device number: %d" % device


   factory = BroadcastServerFactory("ws://localhost:%d" % port, debug = debug, debugCodePaths = debug, interval = interval, device=device)

   factory.protocol = BroadcastServerProtocol
   factory.setProtocolOptions(allowHixie76 = True)
   listenWS(factory)

   webdir = File(".")
   web = Site(webdir)
   reactor.listenTCP(8080, web)
   print "\nEverything up and running!"
   reactor.run()

#kickstart
if __name__ == '__main__':
   main()
