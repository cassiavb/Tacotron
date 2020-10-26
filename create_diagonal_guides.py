#Plot attention matrix for to be "nearly diagonal"
import numpy
from utils.text import text_to_sequence
import os, argparse
from utils import hparams as hp
import pickle


def get_attention_guide(xdim, ydim, g=0.2):
    '''Guided attention (page 3 in the paper.) '''
    W = np.zeros((xdim, ydim), dtype=np.float32)
    for n_pos in range(xdim):
        for t_pos in range(ydim):
            W[n_pos, t_pos] = 1 - np.exp(-(t_pos / float(ydim) - n_pos / float(xdim)) ** 2 / (2 * g * g))
    return W


def create_attention_guides(fpath):

    with open(f'{fpath}/dataset.pkl', 'rb') as f:
          dataset = pickle.load(f)

    for (item_id, len) in dataset:
        dataset_ids += [item_id]
        mel_lengths += [len]

    with open(f'{fpath}/text_dict.pkl', 'rb') as f:
          text_dict = pickle.load(f)

    for item_id in dataset_ids:
      x = text_to_sequence(text_dict[item_id], ['blizz_cleaners'])
      text_lengths = [len(x)]

    for id in enumerate(datatset_ids):

      attfile = os.path.join(fpath, "diagonal_attention_guides", dataset_ids[id] , '.npy')
      att = get_attention_guide(text_lengths[id], mel_lengths[id], g=0.2)
      np.save(attfile, att)


if __name__=="__main__":

    parser = argparse.ArgumentParser(description='Create diagonal attention guides')
    parser.add_argument('--hp_file', metavar='FILE', default='hparams.py', help='The file to use for the hyperparameters')
    args = parser.parse_args()


    hp.configure(args.hp_file)  # Load hparams from file

    path = hp.data_path
    create_attention_guides(path)
