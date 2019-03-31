import argparse
from collections import defaultdict
from pathlib import Path

import numpy as np
import sentencepiece as spm
import tqdm


UNK = '<unk>'
END_OF_LINE = '<endofline>'
END_OF_TEXT = '<endoftext>'


def sp_train():
    # TODO consider moving to fire
    parser = argparse.ArgumentParser(
        description='build sentencepiece model on train subset of the corpora')
    arg = parser.add_argument
    arg('corpora', nargs='+',
        help='corpus roots, containing train/valid/test splits')
    arg('sp_text', help='text file for sentencepiece model '
                        '(will be used as-is if exists)')
    arg('sp_model_prefix', help='path (prefix) to output sentencepiece model')
    arg('--vocab-size', type=int, default=50000)
    arg('--input-sentence-size', type=int , default=0)
    arg('--character-coverage', type=float, default=1.0)
    args = parser.parse_args()

    sp_text = Path(args.sp_text)
    if sp_text.exists():
        print(f'Using existing "{sp_text}", remove and re-run if it is stale.')
    else:
        paths = []
        print(f'Reading corpora: {args.corpora}')
        for corpus_root in map(Path, args.corpora):
            train_root = corpus_root / 'train'
            corpus_paths = list(train_root.glob('**/*.txt'))
            if not corpus_paths:
                parser.error(f'Corpus train split {train_root} looks empty, '
                             f'no text files found')
            paths.extend(corpus_paths)
        try:
            with sp_text.open('wt', encoding='utf8') as sp_text_file:
                for path in tqdm.tqdm(
                        paths, desc='building sentencepiece input'):
                    with path.open('rt', encoding='utf8') as f:
                        for line in f.readlines():
                            if line.strip():
                                sp_text_file.write(line)
        except Exception:
            if sp_text.exists():
                sp_text.unlink()
            raise

    spm.SentencePieceTrainer.train(' '.join([
        f'--input={sp_text}',
        f'--model_prefix={args.sp_model_prefix}',
        f'--vocab_size={args.vocab_size}',
        f'--model_type=bpe',
        f'--max_sentence_length=16384',
        f'--bos_id=-1',
        f'--eos_id=-1',
        f'--unk_piece={UNK}',
        f'--control_symbols={END_OF_LINE},{END_OF_TEXT}',
        f'--character_coverage={args.character_coverage}',
        f'--shuffle_input_sentence=1',
        f'--input_sentence_size={args.input_sentence_size}',
    ]))


def sp_encode():
    parser = argparse.ArgumentParser(
        description='encode corpus with a sentencepiece model')
    arg = parser.add_argument
    arg('corpora', nargs='+',
        help='corpus roots, containing train/valid/test splits')
    arg('sp_model', help='path to output model')
    arg('output', help='path to the output directory, '
                       'which will contain train.npy, valid.npy and test.npy')
    args = parser.parse_args()

    sp_model = spm.SentencePieceProcessor()
    assert sp_model.load(args.sp_model)
    eot = sp_model.PieceToId(END_OF_TEXT)
    eol = sp_model.PieceToId(END_OF_LINE)
    dtype = np.uint16 if len(sp_model) < 2**16 - 1 else np.uint32

    print(f'Reading corpora: {args.corpora}')
    encoded_splits = defaultdict(list)
    for corpus_root in map(Path, args.corpora):
        for split in ['train', 'valid', 'test']:
            split_root = corpus_root / split
            split_paths = list(split_root.glob('**/*.txt'))
            if not split_paths:
                parser.error(f'Corpus {split} split {split_root} looks empty, '
                             f'no text files found')
            for path in tqdm.tqdm(split_paths, desc=str(split_root)):
                encoded = []
                with path.open('rt', encoding='utf8') as f:
                    for line in f.readlines():
                        encoded.extend(sp_model.EncodeAsIds(line))
                        encoded.append(eol)
                    encoded.append(eot)
                encoded_splits[split].append(np.array(encoded, dtype=dtype))

    output_root = Path(args.output)
    output_root.mkdir(exist_ok=True, parents=True)
    for split in ['train', 'valid', 'test']:
        split_path = output_root / f'{split}.npy'
        print(f'Saving encoded split {split} to {split_path}')
        encoded = np.concatenate(encoded_splits[split])
        assert encoded.dtype == dtype
        np.save(split_path, encoded)

