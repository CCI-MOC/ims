import Pyro4
import json

name_server_address = '192.168.122.34'
#Starting the NameServer
Pyro4.naming.startNSloop(host=name_server_address,port=9092)
