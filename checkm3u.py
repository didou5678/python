# -*- coding: UTF-8 -*-
import re
import socket
import select
import http.client
from datetime import datetime
import time
import argparse

'''
节目解析方法
#EXTINF:-1 tvg-name="xxx" tvg-id="CCTV1",CCTV1
1.匹配任意一个没有才继续下一个匹配 tvg-name 
2. ,XXXX
3. tvg-id
4. 如果都没有 则显示为空
'''
'''
url或地址解析方法
组播
igmpproxy播放格式 udp|rtp://239.xxx.xxx.xxx:yyyy
udpxy播放格式 https?://xxxx/rtp|udp/239.xxx.xxx.xxx:yyyy

'''

_VERBOSE=0
def debug_print(*args,**kwargs):
  if _VERBOSE:
    print(*args,**kwargs)

#组播探测 成功返回True
def muitlcastprobe(maddr: str,mport: int,timeout: float=2.0) -> bool:
    def isrtp(rdata):
      if(len(rdata)<13): return False
    #10000000  00100001 第一个字节高2位==rtp版本,iptv使用2,第二个字节 底7位 为媒体类型 iptv为 MPEG-2 TS 流 ==0x21, 第13个字节为47  Sync Byte
      return  ((rdata[0] >> 6 & 0x03) == 2) and ((rdata[1] >>1 & 0x7F) ==16) and (rdata[12]==0x47)
    
    res=False
    sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM,socket.IPPROTO_UDP)
    sock.setsockopt(socket.IPPROTO_IP,socket.IP_ADD_MEMBERSHIP,socket.inet_aton(maddr)+socket.inet_aton("0.0.0.0"))
    sock.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1) 
    sock.settimeout(timeout)
    sock.bind(("0.0.0.0",mport))
    rl,_,_=select.select([sock],[],[],timeout)
    if rl:
      rdata,_=sock.recvfrom(16)
      res=isrtp(rdata)
    sock.setsockopt(socket.IPPROTO_IP,socket.IP_DROP_MEMBERSHIP,socket.inet_aton(maddr)+socket.inet_aton("0.0.0.0"))
    sock.close()
    return res
        

def udpxyprobe(httpsrv:str,port:int,reqpath:str,timeout:float=2.0)-> bool:
  ret=False
  conn=None
  try:
    httpsrv=socket.gethostbyname(httpsrv)
    conn=http.client.HTTPSConnection(httpsrv,port,timeout)  
 
    if conn==None: 
      return False
    conn.request("GET",reqpath)
    resp=conn.getresponse()

    if resp.status != 200:
      conn.close() 
      return ret

    rdata=resp.read(1)
    if rdata[0] == 0x47: #ts流 Sync边界
      ret=True

  except:
    pass
  
  finally:
    if conn:
      conn.close()
    return ret

#手动构造http      
def udpxyprobe2(httpsrv:str,port:int,reqpath:str,timeout:float=2.0)->bool:
  sock=None
  try:  
    httpsrv=socket.gethostbyname(httpsrv)
    sock=socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    if sock.connect_ex((httpsrv,port)):
      return False
    
    
    request = (
                f"GET {reqpath} HTTP/1.1\r\n"
                f"Host: {httpsrv}\r\n"
                "Connection: close\r\n"
                "\r\n"
            )
    sock.send(request.encode("utf-8"))
    rl=select.select([sock],[],[],timeout)
    if rl:
      rdata = sock.recv(256)
      if not rdata:
        return False
      rdata=b"" + rdata
      #print(rdata)
      if re.match(rb"^http/\d.\d 200",rdata,re.I):
         req= (
           f"GET {reqpath} HTTP/1.1\r\n"
           f"HTTP/1.1\r\n"
           "\r\n"
         ).encode()

         sock.send(req)
      
         rdata=sock.recv(184)
         #rdata=b""+rdata
         #print(rdata.hex(' '))
         if rdata[0] == 0x47:
           return True
    else:
      return False

  except Exception as e:
     print(f"{e}")
  finally:
    if sock:
      sock.close()    


def mcscanm3u8file(m3ufile:str,outfile_vaild:str,outfile_invaild:str,timeout:float=2.0,interval:float=1.0):
 try:
    file_in=open(f'{m3ufile}','r')
    file_out_vaild=open(f'{outfile_vaild}','w',buffering=1)
    file_out_invaild=open(f'{outfile_invaild}','w',buffering=1)
    
    file_out_vaild.write(f"#EXTM3U name=可用节目表-{datetime.now().strftime('%Y-%m-%d')}\n")
    file_out_invaild.write(f"#EXTM3U name=不可用节目表-{datetime.now().strftime('%Y-%m-%d')}\n")
    desc_line=None
    addr_line=None
    while True:
      line=file_in.readline()
      if not line:
        break
      line=line.strip()
      res=re.match(r"^#EXTINF:-1|^#EXTINF:\d+",line)
      if res:
        res=re.search(r"tvg-id=.+|,.+|tvg-name=.+",line,re.I)
        if res:
          desc_line=line
          debug_print(f"{desc_line}")
          addr_line=file_in.readline()
          if not addr_line:
            break
          addr_line=addr_line.strip()
          debug_print(f"{addr_line}")
          #res=re.search(r"(rtp|udp)(://|/)\b(22[4-9]|23[0-9])\.((25[0-5]|2[0-4]\d|[01]?\d\d?)\.){2}(25[0-5]|2[0-4]\d|[01]?\d\d?)\b:(?:[1-9]\d{0,3}|[1-5]\d{4}|6[0-4]\d{3}|655[0-2]\d|6553[0-5])",addr_line)
          res=re.search(r"(^rtp://|^udp://)\b(22[4-9]|23[0-9])\.",addr_line,re.I)
          if res:
            # rtp/udp 播放类型
            addrpart=addr_line.split(':')
            if addrpart:
              addrpart[1]=addrpart[1].replace("//","")
              if muitlcastprobe(addrpart[1],int(addrpart[2])):
                 file_out_vaild.writelines([f"{desc_line}\n",f"{addr_line}\n"])
                 debug_print(f"result: successed.\n")
                 time.sleep(interval)
              else:
                file_out_invaild.writelines([f"{desc_line}\n",f"{addr_line}\n"])
                debug_print(f"result: failure.\n")
              continue
         
          res=re.search(r"http://",addr_line,re.I)
          if res:
            #udpxy 播放类型

              #使用http 连接udpxy   
              addrpart=addr_line.split('/')
              connpart=addrpart[2].split(':')
              if udpxyprobe2(connpart[0],int(connpart[1]),f"/{addrpart[3]}/{addrpart[4]}"):
                  file_out_vaild.writelines([f"{desc_line}\n",f"{addr_line}\n"])
                  debug_print(f"result: successed.\n")  
                  time.sleep(interval)
              else:
                  file_out_invaild.writelines([f"{desc_line}\n",f"{addr_line}\n"])
                  debug_print(f"result: failure.\n")
              continue
 except Exception as e:
   print(str(e))
    
 finally:
    file_in.close()
    file_out_vaild.write("#EXT-X-ENDLIST\n")
    file_out_invaild.write("#EXT-X-ENDLIST\n")
    file_out_vaild.close()
    file_out_invaild.close()



def main():
  argparser = argparse.ArgumentParser(
  description="read a m3u8 file and checking vaild for each playlist",
  formatter_class=argparse.RawTextHelpFormatter,
  epilog="""
  example1: python3 %(prog)s --infile-m3u8 iptv_http.m3u --outfile-vaild /tmp/m3uscan_vaild.m3u --outfile-invaild /tmp/m3uscan_invaild.m3u -v
  """
  )

  argparser.add_argument('-i','--infile-m3u8',type=str,required=False,help='一个iptv的m3u8文件')
  argparser.add_argument('-o','--outfile-vaild',type=str,required=False,default='iptv-vaild.m3u',help='输出有效节目的m3u8文件')
  argparser.add_argument('-e','--outfile-invaild',type=str,required=False,default='iptv-invaild.m3u',help='输出无效节目的m3u8文件')
  argparser.add_argument('-t','--timeout',type=float,default=2.0,required=False,help='报文接收超时,单位秒')
  argparser.add_argument('-I','--interval',type=float,default=1.0,required=False,help='发包间歇,单位秒,防止发包太快导致对端无响应')
  argparser.add_argument('-v','--verbose',action='store_true',required=False,help='输出过程')
  args = argparser.parse_args()
  infile=args.infile_m3u8
  outfile_vaild=args.outfile_vaild
  outfile_invaild=args.outfile_invaild
  timeout=args.timeout
  interval=args.interval
  global _VERBOSE
  _VERBOSE=args.verbose 


  debug_print(f"open file: {infile}")
  debug_print(f"prepare vaild file: {outfile_vaild}")
  debug_print(f"prepare invaild file: {outfile_invaild}")
  debug_print("\n")
  mcscanm3u8file(infile,outfile_vaild,outfile_invaild,timeout,interval)




 


if __name__ == "__main__":
   #mcscanm3u8file("/home/dido/下载/iptv_rtp_电信.m3u","/tmp/m3uscan_reach.m3u","/tmp/m3uscan_unreach.m3u",1.0,0)
  main()

 
