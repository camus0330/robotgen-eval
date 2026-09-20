"""Verify one simulation MP4 and extract explicitly requested review frames."""
import argparse
import json
import struct
import subprocess
from pathlib import Path


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True,help='Directory containing simulation.mp4')
    parser.add_argument('--frames',type=float,nargs='*',default=[],help='Review frame times in seconds')
    args=parser.parse_args();video=args.run/'simulation.mp4'
    info=json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0','-show_entries',
                    'stream=codec_name,pix_fmt,r_frame_rate,nb_frames,width,height:format=duration','-of','json',str(video)]))
    stream=info['streams'][0]
    if stream['codec_name']!='h264' or stream['pix_fmt']!='yuv420p' or stream['r_frame_rate']!='25/1':
        raise ValueError(f'Expected H.264/yuv420p/25 fps, received {stream}')
    subprocess.run(['ffmpeg','-v','error','-i',str(video),'-f','null','-'],check=True)
    atoms=[]
    with video.open('rb') as source:
        while True:
            offset=source.tell();header=source.read(8)
            if not header:break
            if len(header)!=8:raise ValueError('Truncated MP4 atom header')
            size,kind=struct.unpack('>I4s',header);header_size=8
            if size==1:
                size=struct.unpack('>Q',source.read(8))[0];header_size=16
            if size==0:size=video.stat().st_size-offset
            if size<header_size or offset+size>video.stat().st_size:raise ValueError('Invalid MP4 atom length')
            atoms.append(dict(type=kind.decode(),offset=offset,size=size));source.seek(offset+size)
    moov=next(a['offset'] for a in atoms if a['type']=='moov')
    mdat=next(a['offset'] for a in atoms if a['type']=='mdat')
    if moov>=mdat:raise ValueError('MP4 lacks faststart: moov must precede mdat')
    extracted=[]
    for time in args.frames:
        if not 0<=time<float(info['format']['duration']):raise ValueError(f'Frame time outside video: {time}')
        frame=args.run/f'frame_{time:g}s.png'
        subprocess.run(['ffmpeg','-v','error','-ss',str(time),'-i',str(video),'-frames:v','1','-y',str(frame)],check=True)
        if not frame.is_file() or not frame.stat().st_size:raise ValueError(f'Frame extraction failed: {frame}')
        extracted.append(dict(time_s=time,file=frame.name))
    info.update(top_level_atoms=atoms,decode_ok=True,faststart=True,extracted_frames=extracted)
    (args.run/'media_check.json').write_text(json.dumps(info,indent=2)+'\n')
    print(json.dumps(dict(video=str(video),stream=stream,decode_ok=True,faststart=True,extracted_frames=extracted),indent=2))


if __name__=='__main__':main()
