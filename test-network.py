#!/usr/bin/python

"""
Simple example of setting network and CPU parameters

NOTE: link params limit BW, add latency, and loss.
There is a high chance that pings WILL fail and that
iperf will hang indefinitely if the TCP handshake fails
to complete.
"""

import argparse
from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import CPULimitedHost, Controller, RemoteController, OVSSwitch
from mininet.link import TCLink
from mininet.util import dumpNodeConnections
from mininet.log import setLogLevel, output
from mininet.cli import CLI
from tempfile import mkstemp
from subprocess import check_output, call
import re
import time
import os

from sys import argv

class SquareTopo(Topo):
    "Square switch topology with five hosts"
    def __init__(self, externalqos, **opts):
        Topo.__init__(self, **opts)
        switch1 = self.addSwitch('s1', cls=OVSSwitch, failMode="standalone")
        switch2 = self.addSwitch('s2', cls=OVSSwitch, failMode="standalone")
        switch3 = self.addSwitch('s3', cls=OVSSwitch, failMode="standalone")
        switch4 = self.addSwitch('s4', cls=OVSSwitch, failMode="standalone")
        host1 = self.addHost("h1", mac='0a:00:00:00:00:01')
        host2 = self.addHost("h2", mac='0a:00:00:00:00:02')
        host3 = self.addHost("h3", mac='0a:00:00:00:00:03')
        host4 = self.addHost("h4", mac='0a:00:00:00:00:04')
        host5 = self.addHost("h5", mac='0a:00:00:00:00:05')

        if externalqos == False:
            #note in the code HTB seems to be the default but does not work well
            # spent some time trying out these. In practice it may depend upon the TC values
            # put in by mininet/mininet/link.py so this may vary from kernel to kernel
            # and different mininet releases
            # the best results seem to be with the following:
            use_tbf=True
            use_hfsc=False
            # have not tried this, probably not relevant unless the app makes use of ECN
            enable_ecn=False
            # while in theory it makes sense to enable this, the problem is that
            # it might delete some of the essential iperf packets so probably best left off
            enable_red=False
            self.addLink(switch1,host1,bw=20,use_tbf=use_tbf,
                         use_hfsc=use_hfsc,enable_ecn=enable_ecn,enable_red=enable_red)
            self.addLink(switch2,host2,bw=20,use_tbf=use_tbf,
                         use_hfsc=use_hfsc,enable_ecn=enable_ecn,enable_red=enable_red)
            self.addLink(switch3,host3,bw=20,use_tbf=use_tbf,
                        use_hfsc=use_hfsc,enable_ecn=enable_ecn,enable_red=enable_red)
            self.addLink(switch4,host4,bw=20,use_tbf=use_tbf,
                         use_hfsc=use_hfsc,enable_ecn=enable_ecn,enable_red=enable_red)
            
            self.addLink(switch1,switch2,bw=10,use_tbf=use_tbf,
                         use_hfsc=use_hfsc,enable_ecn=enable_ecn,enable_red=enable_red)
            self.addLink(switch2,switch3,bw=10,use_tbf=use_tbf,
                         use_hfsc=use_hfsc,enable_ecn=enable_ecn,enable_red=enable_red)
            self.addLink(switch3,switch4,bw=10,use_tbf=use_tbf,
                         use_hfsc=use_hfsc,enable_ecn=enable_ecn,enable_red=enable_red)
            self.addLink(switch4,switch1,bw=10,use_tbf=use_tbf,
                         use_hfsc=use_hfsc,enable_ecn=enable_ecn,enable_red=enable_red)
            # putting host5 last keeps the port numbers in a nice order
            # ie 1 for primary host, 2,3 for switch links, this
            # one is an odd one out in port 4
            self.addLink(switch1,host5,bw=20,use_tbf=use_tbf,
                         use_hfsc=use_hfsc,enable_ecn=enable_ecn,enable_red=enable_red)
        else:
            self.addLink(switch1,host1)
            self.addLink(switch2,host2)
            self.addLink(switch3,host3)
            self.addLink(switch4,host4)
            
            self.addLink(switch1,switch2)
            self.addLink(switch2,switch3)
            self.addLink(switch3,switch4)
            self.addLink(switch4,switch1)
            # putting host5 last keeps the port numbers in a nice order
            # ie 1 for primary host, 2,3 for switch links, this
            # one is an odd one out in port 4
            self.addLink(switch1,host5)
        
    def afterStartConfig(self, net, sdn, externalqos):
        """configuration to topo that needs doing after starting"""
        s1=net.getNodeByName('s1')
        s2=net.getNodeByName('s2')
        s3=net.getNodeByName('s3')
        s4=net.getNodeByName('s4')
        # this is fairly manual, we want to make s1-s2 link off in STP
        # so setting S4 to be root and s3 secondary root
        # also enabling rstp for quicker startup
        if sdn == False :
            s4.cmd("ovs-vsctl set Bridge s4 rstp_enable=true ")
            s4.cmd("ovs-vsctl set Bridge s4 other_config:rstp-priority=4096")
            s3.cmd("ovs-vsctl set Bridge s3 rstp_enable=true")
            s3.cmd("ovs-vsctl set Bridge s3 other_config:rstp-priority=28672")
            s1.cmd("ovs-vsctl set Bridge s1 rstp_enable=true")
            s2.cmd("ovs-vsctl set Bridge s2 rstp_enable=true")
            
        if externalqos == True:
            setTCcmd=os.path.dirname(os.path.realpath(__file__))+"/set-qos.sh"
            # get the list of interfaces that are between switches only (ie ignore lo and host interfaces)
            tcInterfaces = ''
            for sw in net.switches:
                for intf in sw.intfList():
                    if intf.link:
                        intfName = intf.name
                        # this is brittle, but ok if we keep to our simple switch/host naming
                        intfs = [ intf.link.intf1, intf.link.intf2 ]
                        intfs.remove( intf )
                        linkName = intf.name + ' ' + intfs[0].name
                        if (bool(re.search("^s.*s.*$", linkName))):
                            tcInterfaces = tcInterfaces + " " + intf.name
            print("*** Setting qos externally using TC commands from " + setTCcmd)
            print("    on interfaces " + tcInterfaces)
            cmd = setTCcmd + " " + tcInterfaces
            retVal = call(cmd, shell=True)
            if retVal != 0:
                print("*** error setting qos")
    
def throughput_H1_H2(net):
    print("*** test1 Testing Throughput between H1 and H2 (no background traffic)")
    print("Please wait for 30 seconds")
    h1 = net.getNodeByName("h1")
    h2 = net.getNodeByName("h2")
    h3 = net.getNodeByName("h3")
    h4 = net.getNodeByName("h4")
    # for udp
    #h2.cmd("iperf -s -u &")
    h2.cmd("iperf -s &")
    time.sleep(4)
    # for udp
    #h1out = h1.cmd("iperf -c 10.0.0.2 -u -b 10M -t 30 -y c -x CDMS")
    h1out = h1.cmd("iperf -c 10.0.0.2 -t 30 -y c")
    h1out = h1out.split(",")
    if len(h1out) < 9:
        print("*** Test Failed Error, length of reply only had " + str(len(h1out)) + " field(s)")
        print("***      note that these tests might fail due to the fact the network is being overloaded")
        print("***      you can run it again later from the command line as test1.")
    else:
        tp=float(h1out[8])/1000000.0
        print("*** Results Throughput=" +str(tp) + "Mb/s")
    print("")

def throughput_H1_H2andH4_H3(net):
    print("*** test2 Testing Throughput between H1 and H2 with background traffic between H4 and H3")
    print("Please wait for 30 seconds")
    h1 = net.getNodeByName("h1")
    h2 = net.getNodeByName("h2")
    h3 = net.getNodeByName("h3")
    h4 = net.getNodeByName("h4")
    h2.cmd("iperf -s &")
    h3.cmd("iperf -s &")
    time.sleep(1)
    h1mon = h1.sendCmd("iperf -c 10.0.0.2 -t 30 -y c")
    h4out = h4.cmd("iperf -c 10.0.0.3 -t 30 -y c")
    h4out = h4out.split(",")
    if len(h4out) < 9:
        print("*** Test Failed Error, length of reply only had " + str(len(h4out)) + " field(s)")
        print("***      note that these tests might fail due to the fact the network is being overloaded")
        print("***      you can run it again later from the command line as test1.")
    else:
        tp=float(h4out[8])/1000000.0
        print("*** Results Throughput from H4=" +str(tp) + "Mb/s")
    h1out= h1.waitOutput()
    h1out = h1out.split(",")
    if len(h1out) < 9:
        print("*** Test Failed Error, length of reply only had " + str(len(h1out)) + " field(s)")
        print("***      note that these tests might fail due to the fact the network is being overloaded")
        print("***      you can run it again later from the command line as test1.")
    else:
        tp=float(h1out[8])/1000000.0
        print("*** Results Throughput from H1=" +str(tp) + "Mb/s")
    print("")

def throughput_H1_H2andH5_H2(net):
    print("*** test3 Testing Simultaneous Throughput H1 to H2 and H5 to H2")
    print("Please wait for 30 seconds")
    h1 = net.getNodeByName("h1")
    h2 = net.getNodeByName("h2")
    h3 = net.getNodeByName("h3")
    h4 = net.getNodeByName("h4")
    h5 = net.getNodeByName("h5")
    h2.cmd("iperf -s &")
    time.sleep(1)
    h1mon = h1.sendCmd("iperf -c 10.0.0.2 -t 30 -y c")
    h5out = h5.cmd("iperf -c 10.0.0.2 -t 30 -y c")
    h5out = h5out.split(",")
    if len(h5out) < 9:
        print("*** Test Failed Error, length of reply only had " + str(len(h1out)) + " field(s)")
        print("***      note that these tests might fail due to the fact the network is being overloaded")
        print("***      you can run it again later from the command line as test1.")
    else:
        tp=float(h5out[8])/1000000.0
        print("*** Results Throughput from H5=" +str(tp) + "Mb/s")

    h1out= h1.waitOutput()
    h1out = h1out.split(",")
    if len(h1out) < 9:
        print("*** Test Failed Error, length of reply only had " + str(len(h1out)) + " field(s)")
        print("***      note that these tests might fail due to the fact the network is being overloaded")
        print("***      you can run it again later from the command line as test1.")
    else:
        tp=float(h1out[8])/1000000.0
        print("*** Results Throughput from H1=" +str(tp) + "Mb/s")
    print("")

def arp_and_ping_H4_H3(net):
    print("*** test4 Ping h4 to h3 10 times (including arp at beginning)")
    if net.argsSdn == True:
        print("    waiting 10s for any old flow rules to flush out")
        # I lied, lets wait 12 seconds just in case
        time.sleep(15)
    h4 = net.getNodeByName("h4")
    h3 = net.getNodeByName("h3")
    h4.cmd("arp -d 10.0.0.3")
    h3.cmd("arp -d 10.0.0.4")
    h4.cmdPrint("ping -c 10 10.0.0.3")
    print("")

def noarp_and_ping_H4_H3(net):
    h4 = net.getNodeByName("h4")
    h4out=h4.cmd("ping -c 1 10.0.0.3")
    print("*** test5 Ping h4 to h3 10 times (no arp at beginning)")
    if net.argsSdn == True:
        print("    waiting 10s for any old flow rules to flush out")
        # I lied, lets wait 12 seconds just in case
        time.sleep(15)
    h4.cmdPrint("ping -c 10 10.0.0.3")
    print("")


#Wrappers needed for command line
def test1(self,line):
    net = self.mn
    throughput_H1_H2(net)

def test2(self,line):
    net = self.mn
    throughput_H1_H2andH4_H3(net)
    
def test3(self,line):
    net = self.mn
    throughput_H1_H2andH5_H2(net)
    
def test4(self,line):
    net = self.mn
    arp_and_ping_H4_H3(net)
    
def test5(self,line):
    net = self.mn
    noarp_and_ping_H4_H3(net)
    
    
def printSTP():
    # get the list of ports, this is nasty, but works
    ports=check_output('sudo ovs-vsctl list port | grep name | grep "-" | sed "s/.*name.*: \\"\(.*\)\\"$/\\1/" | sort',shell=True)
    # for each port
    for i in ports.splitlines():
        reply=check_output("/usr/bin/ovs-vsctl list port " + i,shell=True)
        reply=reply.replace("\n"," ")
        # again nasty
        filtered = re.sub(r'.*name[^"]+"([^"]+)".*rstp_port_role(.*),.*$',r'\1\2',reply)
        print(filtered)
    print("")

    

if __name__ == '__main__':
    # parse the command line arguments
    parser = argparse.ArgumentParser()
    parser.add_argument("-c","--controller", help="sdn controller ip [127.0.0.1]", default="127.0.0.1")
    parser.add_argument("-p","--port", type=int, help="sdn controller port [6633]", default=6633)
    parser.add_argument("-t","--tests", action='store_true', help="run tests automatically")
    parser.add_argument("-e","--externalqos", action='store_true', help="configure qos outside mininet")
    group=parser.add_mutually_exclusive_group()
    group.add_argument("-s", "--sdn", action='store_true', help="enable SDN mode (the default)")
    group.add_argument("-n", "--normal", action='store_true', help="enable STP mode (not the default)")
    args = parser.parse_args()
    if args.normal == False:
        args.sdn = True
    if args.sdn == True:
        print("Running in SDN mode")
    else:
        print("Running in STP mode")
        
    # kill any old mininet first
    os.system("mn -c > /dev/null 2>&1")    
    setLogLevel( 'info' )
    topo = SquareTopo(args.externalqos)
    net = Mininet( topo=topo,
                   link=TCLink,
                   controller=None)
    net.argsSdn=args.sdn
    if args.sdn :
        net.addController( 'c0', controller=RemoteController, ip=args.controller, port=args.port )

    net.start()
    topo.afterStartConfig(net,args.sdn,args.externalqos)
    #print "*** Dumping host connections"
    #dumpNodeConnections(net.hosts)
    #print "*** Dumping switch connections"
    #dumpNodeConnections(net.switches)
    print("Waiting for startup and network to settle (please wait 5 seconds)")
    time.sleep(5)
    if args.sdn == False:
        print("*** STP state of the switches")
        printSTP()
        print("*** done printing STP state")
        print("")
    net.pingAll()
    print("")
    if args.tests == True :
        throughput_H1_H2(net)
        print("waiting 20s for the buffers to empty")
        time.sleep(20)
        throughput_H1_H2andH4_H3(net)
        print("waiting 20s for the buffers to empty")
        time.sleep(20)
        throughput_H1_H2andH5_H2(net)
        print("waiting 20s for the buffers to empty")
        time.sleep(20)
        arp_and_ping_H4_H3(net)
        time.sleep(2)
        noarp_and_ping_H4_H3(net)
        
    CLI.do_test1 = test1
    CLI.do_test2 = test2
    CLI.do_test3 = test3
    CLI.do_test4 = test4
    CLI.do_test5 = test5
    print("enter \"quit\" to exit or issue mininet commands if you know them")
    print("you can run the tests using the commands \"test1\" or \"test2\" ....")
    CLI(net)
    net.stop()
