import numpy as np
from pathlib import Path
from scipy.spatial.distance import cdist
import os, codecs, re
from utils import hparams as hp
import argparse

def plain_phone_label_to_monophones(labfile):
    labels = np.loadtxt(labfile, dtype=str, comments='#') ## default comments='#' breaks
    starts = labels[:,0].astype(int)
    ends = labels[:,1].astype(int)
    mono = labels[:,2]
    lengths = (ends - starts) / 10000 ## length in msec
    return (mono, lengths)

def merlin_state_label_to_monophones(labfile):
    labels = np.loadtxt(labfile, dtype=str, comments=None) ## default comments='#' breaks
    starts = labels[:,0].astype(int)[::5]
    ends = labels[:,1].astype(int)[4::5]
    fc = labels[:,2][::5]
    mono = [label.split('-')[1].split('+')[0] for label in fc]
    # return zip(starts, ends, mono)

    lengths = (ends - starts) / 10000 ## length in msec
    return (mono, lengths)

def resample_timings(lengths, from_rate, to_rate, total_duration):
    '''
    lengths: array of durations in msec. Each value is divisible by from_rate.
    Return converted sequence where values are divisible by to_rate.
    If total_duration, increase length of *last* item to match this total_duration.
    '''


    remainder = lengths % from_rate

    if not all(x == 0 for x in remainder):
        return None


    ## find closest valid end given new sample rate
    ends = np.cumsum(lengths)
    new_valid_positions = np.arange(0,ends[-1] + (from_rate*3),float(to_rate))
    distances = cdist(np.expand_dims(ends,-1), np.expand_dims(new_valid_positions, -1))
    in_new_rate = new_valid_positions[distances.argmin(axis=1)]
    if 0:
        print(zip(ends, in_new_rate))

    ## undo cumsum to get back from end points to durations:
    in_new_rate[1:] -= in_new_rate[:-1].copy()

    if total_duration:
        diff = total_duration - in_new_rate.sum()
        assert in_new_rate.sum() <= total_duration, (in_new_rate.sum(), total_duration)
        assert diff % to_rate == 0.0
        in_new_rate[-1] += diff

    return in_new_rate

def match_up(merlin_label_timings, phoneme_label):

    merlin_silence_symbols = ['pau', 'sil', 'skip']
    merlin_label, merlin_timings = merlin_label_timings
    output = []
    timings = []
    m = d = 0

    while m < len(merlin_label) and d < len(phoneme_label):

        if merlin_label[m] in merlin_silence_symbols:
            assert phoneme_label[d].startswith('<'), (phoneme_label[d], merlin_label[m])
            timings.append(merlin_timings[m])
            m += 1
            d += 1
        else:
            if phoneme_label[d].startswith('<'):
                timings.append(0)
                d += 1
            else:
                timings.append(merlin_timings[m])
                m += 1
                d += 1
    assert m==len(merlin_label)
    while d < len(phoneme_label): ## in case punctuation then <_END_> at end of dctts
        timings.append(0)
        d += 1
    return timings

def write_transcript(texts, transcript_file, duration=False):

    f = codecs.open(transcript_file, 'w', 'utf-8')

    for base in sorted(texts.keys()):
        phones = ' '.join(texts[base]['phones'])
        line = '%s||%s|%s'%(base, texts[base]['text'], phones)
        if duration:
            if 'duration' not in texts[base]:
                print('Warning: skip %s because no duration'%(base))
                continue
            dur = ' '.join(np.array(texts[base]['duration'], dtype='str'))
            line += '||%s'%(dur)  ## leave empty speaker ID field
        f.write(line + '\n')
    f.close()
    print('Wrote to %s' %(transcript_file))

def read_transcript(transcript_file):
    texts = codecs.open(transcript_file, 'r', 'utf-8', errors='ignore').readlines()
    texts = [line.strip('\n\r |') for line in texts]
    texts = [t for t in texts if t != '']
    texts = [line.strip().split("|") for line in texts]

    for line in texts:
        assert len(line) == len(texts[0]), line

    transcript = {}

    for text in texts:
        assert len(text) >= 4  ## assume phones
        base, plaintext, normtext, phones = text[:4]
        phones = re.split('\s+', phones)
        transcript[base] = {'phones': phones, 'text': normtext}

    return transcript

def durations_to_attention_matrix(durations):
    '''
    Take array of durations, return selection matrix to replace A in attention mechanism.
    E.g.:
    durations_to_hard_attention_matrix(np.array([3,0,1,2]))
    [[1. 1. 1. 0. 0. 0.]
     [0. 0. 0. 0. 0. 0.]
     [0. 0. 0. 1. 0. 0.]
     [0. 0. 0. 0. 1. 1.]]
    '''
    nphones = len(durations)
    nframes = durations.sum()
    A = np.zeros((nframes, nphones), dtype=np.float32)
    start = 0
    for (i,dur) in enumerate(durations):
        end = start + dur
        A[start:end,i] = 1.0
        start = end
    assert A.sum(axis=1).all() == 1.0
    assert A.sum(axis=0).all() == durations.all()
    return A

def get_attention_guide(xdim, ydim, g=0.2):
    '''Guided attention. DCTTS (following page 3 in paper)'''
    W = np.zeros((xdim, ydim), dtype=np.float32)
    for n_pos in range(xdim):
        for t_pos in range(ydim):
            W[n_pos, t_pos] = 1 - np.exp(-(t_pos / float(ydim) - n_pos / float(xdim)) ** 2 / (2 * g * g))
    return W




def save_guided_attention(matrix, outfile):
    np.save(outfile, matrix, allow_pickle=False)
    print('Created attention guide %s' %(outfile))




def main_work():


   parser = argparse.ArgumentParser(description='Get durations for Tacotron')
   parser.add_argument('--hp_file', metavar='FILE', default='hparams.py', help='The file to use for the hyperparameters')
   args = parser.parse_args()


   hp.configure(args.hp_file)  # Load hparams from file

   transcript_file = Path(f'{hp.data_path}/train_dctts.csv')
   outfile = Path(f'{hp.data_path}/train_durations_dctts.csv')
   transcript = read_transcript(transcript_file)

   # check if label files exist
   if not os.path.exists(f'{hp.data_path}/labels/label_state_align/'):
       print("No label_state_align directory found!")
       exit()
   if len(os.listdir(f'{hp.data_path}/labels/label_state_align/')) == 0:
       print(f'{hp.data_path}/labels/label_state_align/ is empty')
       exit()
   if not os.path.exists(f'{hp.data_path}/mel'):
        print("No mel directory found!")
        exit()
   if len(os.listdir(f'{hp.data_path}/mel')) == 0:
        print(f'{hp.data_path}/mel is empty')
        exit()

   for labfile in os.listdir(f'{hp.data_path}/labels/label_state_align/'):
       print(f'Processing {labfile} ... ')
       labfile = Path(labfile)
       os.makedirs(f'{hp.data_path}/attention_guides_dctts', exist_ok=True)
       out_guide_file = Path(f'{hp.data_path}/attention_guides_dctts/{labfile.stem}.npy')

       labfile = Path(os.path.join(f'{hp.data_path}/labels/label_state_align/',labfile))
       (mono, lengths) =   merlin_state_label_to_monophones(labfile)


       mel_file = labfile.stem
       mel_features = np.load(f'{hp.data_path}/mel_dctts/{mel_file}.npy')
       print(mel_features.shape)
       audio_msec_length = mel_features.shape[0] * 50
       print(audio_msec_length)
       mel_features_12 = np.load(f'{hp.data_path}/mel/{mel_file}.npy')
       print(mel_features_12.shape)
       audio_msec_length_12 = mel_features_12.shape[1] * 12.5
       print(audio_msec_length_12)
       resampled_lengths = resample_timings(lengths, 5.0, 50.0, total_duration=audio_msec_length)
       print(resampled_lengths)

       resampled_lengths_12 = resample_timings(lengths, 5.0, 12.5, total_duration=audio_msec_length_12)
       print(resampled_lengths)

       exit()
       if resampled_lengths is not None:
           resampled_lengths_in_frames = (resampled_lengths / 50).astype(int)
           timings = match_up((mono, resampled_lengths_in_frames), transcript[labfile.stem]['phones'])


           assert len(transcript[labfile.stem]['phones']) == len(timings), (len(transcript[labfile.stem]['phones']), len(timings), transcript[labfile.stem]['phones'], timings)
           transcript[labfile.stem]['duration'] = timings

           guided_attention_matrix = durations_to_attention_matrix(np.array(timings))
           save_guided_attention(guided_attention_matrix, out_guide_file)

       else:
           print(f'{labfile} was not successfully processed!')

   write_transcript(transcript, outfile, duration=True)







if __name__=="__main__":
    main_work()
