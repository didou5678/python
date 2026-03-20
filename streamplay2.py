# -*- coding: UTF-8 -*-

import subprocess
import os
import time
import threading
import sys
import argparse
import signal


#手动设置该值 不为0 开启
_MYDEBUG=0
def debug_print(*args,**kwargs):
  if _MYDEBUG:
    print(*args,**kwargs)


if not sys.platform.startswith("linux"):
    debug_print("run in linux")
    sys.exit(1) 

#进程退出指令
g_isThisProcExit=False
def handle_thisproc_exit(signum,frame):
   global g_isThisProcExit
   g_isThisProcExit=True
   
   debug_print(f"recv process signal: {signum} {signal.Signals(signum).name}")

signal.signal(signal.SIGTERM, handle_thisproc_exit) 
signal.signal(signal.SIGINT, handle_thisproc_exit) 


def thd_readpipe(pipepath:str,thdlock:"threading.Lock",isexit:list,totalpipe:list): 
    """
    Args:
        :param pipepath: 命名管道路径
        :param thdlock: 线程锁
        :param isexit: 指示当前线程是否继续运行,为True退出
        :param totalpipe: 从管道读取数据的累计,单位字节
    """

    while True:
      fp=os.open(pipepath, os.O_RDONLY | os.O_NONBLOCK)
      while True:
        if isexit[0] == True:
           debug_print("thd_readpipe: recv exit cmd.")
           os.close(fp)
           return  
        #debug_print('thd_readpipe loop')
        try:
          data=os.read(fp,1440)
          #debug_print(f"current: {len(data)}")  
        except BlockingIOError:
          data=b''
          time.sleep(0.1)
          pass

        if data != b'':    
            with thdlock:
                totalpipe[0] +=len(data)
                #debug_print(f"total: {thdargs[1][0]}")
                #在这里将副本流保存到文件或是其他操作 不要阻塞式操作 
        else:
           time.sleep(1.0)
            


#devaudio 为pulse alsa 或其他, audioname为 播放设备 默认为 default, 如pulse类型可指定sink
def playsteam(url:str="",ffvol:int=30,retry:int=3,timeout:int=5,devaudio:str="",audioname:str="default")->None:
    
    if url =="":
        return
    
    PIPEPATH='/tmp/ffmpeg_stream_pipe'

    try:
        if not os.path.exists(PIPEPATH):
            os.mkfifo(PIPEPATH,0o660)
    except:
        return

    if isinstance(ffvol,int) == False:
       ffvol=30
       debug_print(f"{ffvol} is not int type so that setting to ffvol=30")

    ffvol:float = ffvol / 100.0
   
    ishttp=url.startswith(('http://', 'https://','HTTP://','HTTPS://'))
    if devaudio == "" or devaudio == "pulse":
       devaudio=[ "pulse", "-filter:a",f"volume={ffvol}","-name", "ffstreamplay", f"{audioname}"] 
    elif devaudio == "alsa":
       devaudio=[ "alsa","-filter:a",f"volume={ffvol}",f"{audioname}"]

#ffmpeg -y -loglevel quiet   -i http://127.0.0.1:18080/stream     -f pulse -filter:a volume=1.0 -name "11111" default -c:a  copy -f wav -flush_packets 1 pipe:1 > /tmp/ffmpeg_stream_pipe
# -c:a  copy -f wav  如果对 转码无要求 这个cpu占用低 
#  -f flv 
# -c:a libmp3lame 
# -c:a aac -b:a 128k

    ffmpeg_cmd=[
        "ffmpeg",
        "-y",
        "-loglevel","quiet",
        "-i",url,

        "-f",*devaudio,
    
        "-c:a","copy",
        "-f","wav",
        "-flush_packets","1",
         "pipe:1"
    ]
  
    isthdexit=[False]
    total_pipe=[0]
    thdargs=(PIPEPATH,threading.Lock(),isthdexit,total_pipe)
    
    
    

# 线程先跑
# 如果ffmpeg 读不到流或连不上会 退出 或 僵死 

    try:    
       thd=threading.Thread(target=thd_readpipe,args=thdargs,daemon=True,name='thd_readpipe')
       thd.start()                   
    
       for i in range(1,retry+1):
            
            #启动
            fp=os.open(PIPEPATH,os.O_WRONLY)
            proc_ffmpeg= subprocess.Popen(
                ffmpeg_cmd,
                stdin=subprocess.DEVNULL,
                stdout=fp,
                stderr=subprocess.DEVNULL,
                bufsize=0)
            time.sleep(1)     
            old_total=0
            start_tm=time.time()
            while True:
                if g_isThisProcExit:
                   break

                with threading.Lock():
                  new_total= total_pipe[0]

                if old_total < new_total:
                    start_tm=time.time()
                elif time.time() - start_tm  >= timeout:
                    break
                old_total=new_total
                time.sleep(1.0)
            #while end
                
            debug_print(f"cannot recv ffmpeg pipe data [{i}] thus restart ffmpeg")
            if proc_ffmpeg.poll() is None:
                proc_ffmpeg.terminate()
                proc_ffmpeg.wait()
            os.close(fp) 
            if g_isThisProcExit: break
        #for end

       isthdexit[0]=True       
       thd.join()
       os.remove(PIPEPATH)
       debug_print("all retry is fault so that exit program.") 
    except Exception as e:
        print(e)

       





def main():
  
  argparser = argparse.ArgumentParser(
   description="a python3 ffmpeg player",
   formatter_class=argparse.RawTextHelpFormatter)
  
  argparser.add_argument('-i','--input',required=False,type=str,help='要播放的url或本地文件')
  argparser.add_argument('-v','--ffvol',required=False,default=30,type=int,help='ffmpeg解码音量')
  argparser.add_argument('-r','--retry',type=int,required=False,default=10,help='播放失败时重试次数')
  argparser.add_argument('-t','--timeout',type=int,required=False,default=3,help='播放失败等待的秒数')
  argparser.add_argument('-s','--sinkname',type=str,required=False,default="default",help='指定pulse播放sink')
  argparser.add_argument('-d','--devaudio',type=str,required=False,default="pulse",help='指定声音设备pulse或alsa')
  argparser.add_argument('--debug',action='store_true',required=False,help='输出打印信息')

  try:
    args = argparser.parse_args()
  except Exception as e:
    pass

  if args.debug:
     global _MYDEBUG
     _MYDEBUG=1

 #http://127.0.0.1:18080/stream
  playsteam(url=args.input,devaudio=args.devaudio,audioname=args.sinkname,retry=args.retry,timeout=args.timeout,ffvol=args.ffvol)




if __name__ == "__main__":
    main()
