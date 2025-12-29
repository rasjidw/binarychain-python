
import argparse
from itertools import zip_longest
import os
import sys

import binarychain


LINE_LENGTH = 40


def grouper(iterable, n):
    args = [iter(iterable)] * n
    return zip_longest(*args)


def display_binary(data, line_length, non_ascii_char='☐'):
    for row in grouper(data, line_length):
        hex_line = [f'{byte_value:02X}' for byte_value in row if byte_value is not None]
        chars = [chr(byte_value) if byte_value < 128 else non_ascii_char
                 for byte_value in row if byte_value is not None]
        printable_chars = [f'{char} ' if char.isprintable() else non_ascii_char + ' ' for char in chars]
        print(' '.join(hex_line))
        print(' '.join(printable_chars))
        print()


def encode(args):
    output_file = args.output_file
    if output_file == '-' and args.verify:
        print("Can't verify stdout!")
        return

    first_is_prefix = args.prefix is None and not args.noprefix
    prefix = ''
    parts = list()
    if not first_is_prefix:
        prefix = args.prefix if args.prefix is not None else ''
    for index, file in enumerate(args.input_files):
        data = open(file, 'rb').read()
        if index == 0 and first_is_prefix:
            prefix = data.decode('ascii')
        else:
            parts.append(data)
    bc = binarychain.BinaryChain(prefix, parts)
    output = bc.serialise()
    if output_file:
        if args.verify:
            file_data = open(output_file, 'rb').read()
            if file_data != output:
                print('Binary chain file does NOT match expected output')
            else:
                print('Binary chain file matches expected output')
        if output_file == '-':
            sys.stdout.buffer.write(output)
            sys.stdout.buffer.flush()
        with open(output_file, 'wb') as f:
            f.write(output)
    else:
        display_binary(bc.serialise(), LINE_LENGTH)


def _binary_chain_to_files(binary_chain: binarychain.BinaryChain, filename_prefix: str, output_dir: str):
    filename = f'{filename_prefix}-asc-prefix.txt'
    filepath = os.path.join(output_dir, filename)
    with open(filepath, 'w') as f:
        f.write(binary_chain.prefix)

    for index, part_data in enumerate(binary_chain.parts):
        filename = f'{filename_prefix}-bin-part-{index}.data'
        filepath = os.path.join(output_dir, filename)
        with open(filepath, 'wb') as f:
            f.write(part_data)


def decode(args):
    data = open(args.input_file, 'rb').read()
    if not data:
        print('File is empty. No data found.')
        return

    mb = 1024*1024
    reader = binarychain.ChainReader(max_part_size=1*mb, max_chain_size=10*mb, max_chain_length=256)
    chains = reader.get_binary_chains(data)
    if not chains:
        if reader.complete():
            print('SYSTEM ERROR: Flagged as complete but no chains parsed.')
        else:
            print('No complete chain found.')
    if args.output_dir:
        basename = os.path.basename(args.input_file)
        for index, chain in enumerate(chains):
            filename_prefix = f'{basename}-chain-{index+1}'
            _binary_chain_to_files(chain, filename_prefix, args.output_dir)
    else:
        for index, chain in enumerate(chains):
            print(f'Chain {index+1}')
            print(f'Prefix: "{chain.prefix}"')
            if chain.parts:
                for part_index, part in enumerate(chain.parts):
                    print(f'Part {part_index}')
                    display_binary(part, LINE_LENGTH)
            else:
                print('No Binary Parts')
            print('---' * LINE_LENGTH)
            print()


def view(args):
    data = open(args.filename, 'rb').read()
    display_binary(data, LINE_LENGTH)


def main():
    parser = argparse.ArgumentParser(prog="binarychain", description="Binary Chain Parser")
    subparsers = parser.add_subparsers(title='subcommand', required=True, dest="subcommand")

    encode_parser = subparsers.add_parser('encode', help="Encode a binary chain")
    prefix_options = encode_parser.add_mutually_exclusive_group()
    prefix_options.add_argument('--prefix', help="Prefix to binary chain")
    prefix_options.add_argument('--noprefix', action="store_true", help="The prefix is empty")
    encode_parser.add_argument('--output_file',
                               help="Output file - if missing, human readable format is sent to stdout,\n"
                                    "or use '-' for stdout in binary format")
    encode_parser.add_argument('--verify', action='store_true',
                               help="Don't create output file, compare it to expected output")
    encode_parser.add_argument('input_files', nargs='*',
                               help="Files for each binary part - no files means no binary parts.\n"
                                    "First file is prefix unless --prefix or --noprefix is specified")
    encode_parser.set_defaults(func=encode)

    decode_parser = subparsers.add_parser('decode', help="Decode a binary chain")
    decode_parser.add_argument('--output_dir',
                               help="Output directory. If missing prints human readable output to stdout")
    decode_parser.add_argument('input_file', help="File to decode")
    decode_parser.set_defaults(func=decode)

    decode_parser = subparsers.add_parser('view', help="View a binary file")
    decode_parser.add_argument('filename', help="File to view")
    decode_parser.set_defaults(func=view)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
