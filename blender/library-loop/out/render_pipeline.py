"""Run the authorized render and assembly with persistent logs and strict output validation."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import time
import traceback
import zlib

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'out'
FRAMES = ROOT / 'renders/hero'
BLEND = ROOT / 'library_loop_final.blend'
STATE = OUT / 'render-status.json'
MANIFEST = OUT / 'render-manifest.json'
BLENDER = shutil.which('blender')
EXPECTED_BLEND = '611eb0e46f572ed00260d56d67ed78860256868c79c69e63f461eda82f84ca0b'

def utc():
    return datetime.now(timezone.utc).isoformat()

def save_json(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')
    temporary.replace(path)

def check_png(path):
    raw = path.read_bytes()
    if raw[:8] != b'\x89PNG\r\n\x1a\n':
        raise RuntimeError('Invalid PNG signature: ' + str(path))
    offset, packed, dimensions, ended = 8, [], None, False
    while offset < len(raw):
        size = struct.unpack_from('>I', raw, offset)[0]
        kind = raw[offset+4:offset+8]
        data = raw[offset+8:offset+8+size]
        crc = raw[offset+8+size:offset+12+size]
        if len(data) != size or len(crc) != 4 or zlib.crc32(kind+data) != struct.unpack('>I', crc)[0]:
            raise RuntimeError('Invalid PNG chunk CRC: ' + str(path))
        if kind == b'IHDR':
            dimensions = struct.unpack('>IIBBBBB', data)
        elif kind == b'IDAT':
            packed.append(data)
        elif kind == b'IEND':
            ended = True
        offset += 12 + size
        if ended:
            break
    if dimensions != (1920,744,8,6,0,0,0) or not ended or offset != len(raw):
        raise RuntimeError('Unexpected PNG dimensions/format or incomplete image: ' + str(path))
    decoded = zlib.decompress(b''.join(packed))
    if len(decoded) != 744 * (1 + 1920 * 4):
        raise RuntimeError('Incomplete PNG pixel data: ' + str(path))
    return dict(file=path.name, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())

def atoms(raw, begin=0, end=None):
    end = len(raw) if end is None else end
    position = begin
    while position + 8 <= end:
        length, kind = struct.unpack_from('>I4s', raw, position)
        header = 8
        if length == 1:
            length = struct.unpack_from('>Q', raw, position+8)[0]
            header = 16
        if length == 0:
            length = end-position
        if length < header or position+length > end:
            raise RuntimeError('Invalid MP4 atom at ' + str(position))
        yield kind, position+header, position+length
        position += length

def child(raw, parent, kind):
    return next((box for box in atoms(raw, parent[1], parent[2]) if box[0] == kind), None)

def check_mp4(path):
    raw = path.read_bytes()
    top = list(atoms(raw))
    moov = next(box for box in top if box[0] == b'moov')
    tracks = []
    for trak in (box for box in atoms(raw, moov[1], moov[2]) if box[0] == b'trak'):
        mdia = child(raw, trak, b'mdia')
        handler = child(raw, mdia, b'hdlr')
        kind = raw[handler[1]+8:handler[1]+12].decode('ascii')
        mdhd = child(raw, mdia, b'mdhd')
        payload = raw[mdhd[1]:mdhd[2]]
        if payload[0] == 0:
            scale, duration = struct.unpack_from('>II', payload, 12)
        else:
            scale, duration = struct.unpack_from('>IQ', payload, 20)
        stbl = child(raw, child(raw, mdia, b'minf'), b'stbl')
        stsd = child(raw, stbl, b'stsd')
        codec = raw[stsd[1]+12:stsd[1]+16].decode('ascii')
        stts = child(raw, stbl, b'stts')
        entries = struct.unpack_from('>I', raw, stts[1]+4)[0]
        samples = sum(struct.unpack_from('>I', raw, stts[1]+8+i*8)[0] for i in range(entries))
        track = dict(type=kind, codec=codec, duration_seconds=duration/scale, samples=samples)
        if kind == 'vide':
            tkhd = child(raw, trak, b'tkhd')
            width, height = struct.unpack_from('>II', raw, tkhd[2]-8)
            track.update(width=width/65536, height=height/65536, fps=samples/(duration/scale))
        tracks.append(track)
    video = [track for track in tracks if track['type'] == 'vide']
    audio = [track for track in tracks if track['type'] == 'soun']
    if len(video) != 1 or len(audio) != 1:
        raise RuntimeError('MP4 must contain exactly one video and one audio track')
    v = video[0]
    if (v['codec'],v['width'],v['height'],v['samples']) != ('avc1',1920,744,300) or abs(v['fps']-30) > 0.001 or abs(v['duration_seconds']-10) > 0.001:
        raise RuntimeError('Unexpected MP4 video metadata: ' + repr(v))
    if audio[0]['codec'] != 'mp4a' or abs(audio[0]['duration_seconds']-10) > 0.15:
        raise RuntimeError('Unexpected MP4 audio metadata: ' + repr(audio[0]))
    return dict(file=str(path), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(), tracks=tracks)

def main():
    started = time.monotonic()
    status = dict(pid=os.getpid(), started_at=utc(), stage='preflight', completed_frames=0)
    save_json(STATE, status)
    awake = subprocess.Popen(['/usr/bin/caffeinate','-i','-w',str(os.getpid())])
    try:
        if not BLENDER or hashlib.sha256(BLEND.read_bytes()).hexdigest() != EXPECTED_BLEND:
            raise RuntimeError('Blender unavailable or final scene has changed')
        if not (ROOT/'reference/audio_loop.wav').is_file():
            raise RuntimeError('Required music file is missing')
        FRAMES.mkdir(parents=True, exist_ok=True)
        prior = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else None
        existing = list(FRAMES.glob('*.png'))
        if existing and (not prior or prior.get('blend_sha256') != EXPECTED_BLEND):
            raise RuntimeError('Existing render frames are not tied to this final scene')
        for path in existing:
            check_png(path)
        for number in [1,8,21,166,173,250,277]:
            source = ROOT/'renders/final_check'/('f_%04d.png' % number)
            check_png(source)
            target = FRAMES/source.name
            if not target.exists():
                shutil.copy2(source,target)
        save_json(MANIFEST, dict(blend_sha256=EXPECTED_BLEND, source=str(BLEND),
                  scene='HERO', frames=[1,300], fps=30, resolution=[1920,744], samples=96,
                  reused_check_frames=[1,8,21,166,173,250,277], started_at=status['started_at']))

        def run_stage(stage, command, logfile):
            status.update(stage=stage, updated_at=utc(), log=str(logfile))
            save_json(STATE,status)
            print('[pipeline] ' + stage + ' started',flush=True)
            with logfile.open('a') as handle:
                handle.write('\nSTART '+utc()+'\n')
                handle.flush()
                process = subprocess.Popen(command,cwd=ROOT,stdout=handle,stderr=subprocess.STDOUT)
                status['child_pid'] = process.pid
                last = -1
                while process.poll() is None:
                    count = sum(path.stat().st_size > 0 for path in FRAMES.glob('f_*.png'))
                    status.update(completed_frames=count, elapsed_seconds=round(time.monotonic()-started,1),updated_at=utc())
                    save_json(STATE,status)
                    if count != last:
                        print('[pipeline] %s frames=%d/300 elapsed=%.0fs' % (stage,count,status['elapsed_seconds']),flush=True)
                        last = count
                    time.sleep(5)
                if process.returncode:
                    raise RuntimeError('%s exited %d; original output:\n%s' % (stage,process.returncode,'\n'.join(logfile.read_text().splitlines()[-60:])))
            status.pop('child_pid',None)

        run_stage('render',[BLENDER,'-b',str(BLEND),'--python-exit-code','2','-P',str(ROOT/'scripts/render.py'),
                  '--','--scene','HERO','--out',str(FRAMES),'--start','1','--end','300'],OUT/'render-hero.log')
        expected = {'f_%04d.png' % number for number in range(1,301)}
        if {path.name for path in FRAMES.glob('*.png')} != expected:
            raise RuntimeError('Render frame set is incomplete or contains unexpected frames')
        verified = [check_png(FRAMES/name) for name in sorted(expected)]
        save_json(OUT/'frame-validation.json',dict(count=300,resolution=[1920,744],png_crc_and_pixels='passed',frames=verified))
        status['render_completed_at'] = utc()
        status['render_elapsed_seconds'] = round(time.monotonic()-started,2)
        video = OUT/'library_loop_hero.mp4'
        run_stage('assemble',[BLENDER,'-b','--python-exit-code','2','-P',str(ROOT/'scripts/assemble.py'),
                  '--','--hero',str(FRAMES),'--out',str(video)],OUT/'assemble-hero.log')
        metadata = check_mp4(video)
        save_json(OUT/'video-validation.json',metadata)
        status.update(stage='complete_pending_visual_qa',completed_frames=300,completed_at=utc(),
                      elapsed_seconds=round(time.monotonic()-started,2),video=str(video),validation='passed')
        save_json(STATE,status)
        print('[pipeline] COMPLETE '+json.dumps(metadata),flush=True)
    except BaseException as error:
        status.update(stage='failed',error=str(error),failed_at=utc(),elapsed_seconds=round(time.monotonic()-started,2))
        save_json(STATE,status)
        traceback.print_exc()
        raise
    finally:
        if awake.poll() is None:
            awake.terminate()

if __name__ == '__main__':
    main()
