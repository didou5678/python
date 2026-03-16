# -*- coding: UTF-8 -*-

import socket
import select
import argparse
import ipaddress
import re
import time


def muitlcastprobe(sock: "socket.socket",maddr:str,mport:int,timeout:float=2.0, outputobj=None,supress=False,interval:float=1.0) -> bool:

  def isrtp(rdata):
    if(len(rdata)<13): return False
    #10000000  00100001 第一个字节高2位==rtp版本,iptv使用2,第二个字节 底7位 为媒体类型 iptv为 MPEG-2 TS 流 ==0x21, 第13个字节为47  Sync Byte
    return  ((rdata[0] >> 6 & 0x03) == 2) and ((rdata[1] >>1 & 0x7F) ==16) and (rdata[12]==0x47)

  ret=False

  sock.setsockopt(socket.IPPROTO_IP,socket.IP_ADD_MEMBERSHIP,socket.inet_aton(maddr)+socket.inet_aton("0.0.0.0"))
  rl,_,_=select.select([sock],[],[],timeout)
  if rl:
     rdata,fromaddr=sock.recvfrom(16)  
     if rdata:
        print(f"**** respond: rtp://{maddr}:{mport} from addr: {fromaddr}",end=' ',file=outputobj,flush=True)
        if isrtp(rdata) == True:
          ret=True
          print("parsing rtp stream is correct.",file=outputobj,flush=True)
        else:
          print("parsing rtp stream is invaild.",file=outputobj,flush=True)  
     time.sleep(interval)
  elif supress == False:  
    print(f"no respond: rtp://{maddr}:{mport}",file=outputobj,flush=True)
       
  sock.setsockopt(socket.IPPROTO_IP,socket.IP_DROP_MEMBERSHIP,socket.inet_aton(maddr)+socket.inet_aton("0.0.0.0"))
  return ret

#返回值 在只有一个返回的情况 r1一个返回值 r2为None,否则返回2个 r1为min r2为max
def _addrsparse(addr):
  #xxx.xxx.xxx.xxx-zzz.zzz.zzz.zzz 格式匹配
  if re.match(r'^((?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?))-((?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?))$', addr):
    substr_addr_start,substr_addr_end=addr.split('-')
    subint_addr_start= int(ipaddress.IPv4Address(substr_addr_start))
    subint_addr_end= int(ipaddress.IPv4Address(substr_addr_end))
    m=min(subint_addr_start,subint_addr_end)
    subint_addr_end=max(subint_addr_start,subint_addr_end)
    subint_addr_start=m
    return subint_addr_start,subint_addr_end
  else: #单个ipv4地址
    return addr,None  

#返回值 在只有一个返回的情况 r1一个返回值 r2为None,否则返回2个 r1为min r2为max
def _portsparse(port):
  #xxx-zzz 格式匹配
  if re.match(r'^\d+-\d+$', port):
    substr_port_start,substr_port_end = port.split('-')
    subint_port_start=int(substr_port_start)
    subint_port_end=int(substr_port_end)
    m=min(subint_port_start,subint_port_end)
    subint_port_end=max(subint_port_start,subint_port_end)
    subint_port_start=m
    return subint_port_start,subint_port_end
  else:
    return port,None
  


def main():
 argparser = argparse.ArgumentParser(
   description="a python3 iptv rtp mutilcast scan tool",
   formatter_class=argparse.RawTextHelpFormatter,
   epilog="""
   运行时 需要查看是否重复运行或者正在播放iptv 会影响当前进程的报文接收 保证一个实例运行
   example1: python3 %(prog)s -a 239.66.0.1-239.77.0.254,239.77.254.30-239.77.254.1,239.0.0.1 -p 5148,6000-5995,8080-8050 -t 0.5 -I 0.3
   example2: python3 %(prog)s -a 239.77.0.1-239.77.255.255,239.253.0.1-239.253.255.255 -p 5146,5147 -s -f /tmp/scan.log
   侧重于端口探测
   example3: python3 %(prog)s -a 239.30.0.1-239.77.0.10 -p 1024-65535
   example4: python3 %(prog)s -a 239.0.0.1 -p 1024-65535 -t 0.5
   """
  )
 
 argparser.add_argument('-a','--addr',type=str,required=False,default='239.66.0.1-239.77.0.255,239.77.2.1-239.77.2.25,239.0.0.1',help="要扫描的地址,如: -a '239.77.0.1,239.77.1.0-239.77.2.255' ,格式:如果格式为xxxx-yyyy表示连续地址,单个zzzz表示一个地址,每组用逗号分隔")
 argparser.add_argument('-p','--port',type=str,nargs='+',required=False,default='5146,5147,6000-6010',help="扫描端口,可传多个，如 -p '5146,5147,6000-6010',格式:如果格式为xxxx-yyyy 表示连续端口,单个zzzz表示一个端口号,每组用逗号分隔,可反复出现")
 argparser.add_argument('-f','--output-file',type=str,required=False,default=None,help='将扫描结果输出到文件,如果没有指定这个选项则输出到console')
 argparser.add_argument('-t','--timeout',type=float,required=False,default=2.0,help='扫描接收报文超时,单位秒')
 argparser.add_argument('-I','--interval',type=float,required=False,default=1.0,help='每个地址发包间歇 单位秒 防止发包太快导致对端无响应')
 argparser.add_argument('-S','--supress',action='store_true',required=False,help='抑制没有响应输出')

 try:
  args = argparser.parse_args()
 except Exception as e:
  pass

 outputobj=None
 outfile=args.output_file
 if outfile != None:
   outputobj=open(outfile,"w",encoding="utf-8")

 timeout=args.timeout
 argport=args.port
 argaddr=args.addr
 argsuspress=args.supress
 arginterval=args.interval

 try:
  #端口解析
  if isinstance(argport, list):
    argport = ",".join(map(str, argport))  
  #地址解析
  if isinstance(args.addr,list):
   argaddr=",".join(map(str,argaddr))

  portlist=argport.split(',')
  for port in portlist:
      _ps,_pe=_portsparse(port)
      if _pe != None:
       for p in range(_ps,_pe+1):
         sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM,socket.IPPROTO_UDP)
         sock.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1) 
         sock.settimeout(timeout)
         sock.bind(("0.0.0.0",p))
         mcaddrslist=argaddr.split(',')
         for addr in mcaddrslist:
             _as,_ae=_addrsparse(addr)
             if _ae != None:
              for a in range(_as,_ae+1):
                muitlcastprobe(sock,str(ipaddress.IPv4Address(a)),p,timeout,outputobj,argsuspress,arginterval)
             else:
              muitlcastprobe(sock,str(ipaddress.IPv4Address(_as)),p,timeout,outputobj,argsuspress,arginterval)
         
         sock.close 
     
      else:
        port_int=int(port)
        sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM,socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1) 
        sock.settimeout(timeout)
        sock.bind(("0.0.0.0",port_int))
        mcaddrslist=argaddr.split(',')
        for addr in mcaddrslist:
            _as,_ae=_addrsparse(addr)
            if _ae != None:
             for a in range(_as,_ae+1):
               muitlcastprobe(sock,str(ipaddress.IPv4Address(a)),port_int,timeout,outputobj,argsuspress,arginterval)
            else:
             muitlcastprobe(sock,str(ipaddress.IPv4Address(addr)),port_int,timeout,outputobj,argsuspress,arginterval)
        sock.close 
 except KeyboardInterrupt:
   pass

 finally:
  if outfile != None:
   outputobj.close()


if __name__ == "__main__":
   main()
