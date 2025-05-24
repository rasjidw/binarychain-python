from __future__ import annotations

from typing import List

import pytest

from binarychain import BinaryChain, ChainReader, ZERO_SOP_ORD, EOC_ORD, BYTE_LENGTHS_MAP


@pytest.fixture
def sample_chains():
    return {
        "empty": BinaryChain(),
        "hello": BinaryChain("Hello", ["World".encode("ascii")]),
        "empty_part": BinaryChain("Empty Part", [b""]),
        "empty_part_with_more": BinaryChain(
            "Empty Part with more", [b"", b"More Data"]
        ),
    }


def test_serialise(sample_chains: dict[str, BinaryChain]):
    assert sample_chains["empty"].serialise() == b"\xFF"
    assert sample_chains["hello"].serialise() == b"Hello\x81\x05World\xFF"
    assert sample_chains["empty_part"].serialise() == b"Empty Part\x80\xFF"
    assert (
        sample_chains["empty_part_with_more"].serialise()
        == b"Empty Part with more\x80\x81\x09More Data\xFF"
    )


def test_deserialse_single(sample_chains: dict[str, BinaryChain]):
    reader = ChainReader(
        max_part_size=1024 * 1024, max_chain_size=1024 * 1024, max_chain_length=10
    )
    for sample in sample_chains.values():
        print()
        print(sample)
        assert isinstance(sample, BinaryChain)
        data = sample.serialise()
        sample_back = next(reader.get_binary_chains(data))
        assert sample == sample_back
        assert reader.complete()


def split_into_groups(b: bytes, n: int) -> list[bytes]:
    """
    Splits a string into groups of `n` consecutive bytes.
    """
    # Check if `n` is a positive integer.
    if n <= 0:
        raise ValueError("The group size must be a positive integer")

    # Use list comprehension and slicing to split the bytes into groups of `n` characters.
    return [b[i : i + n] for i in range(0, len(b), n)]


def test_deserialise_multiple(sample_chains: dict[str, BinaryChain]):
    empty = sample_chains["empty"]
    hello = sample_chains["hello"]
    empty_part = sample_chains["empty_part"]
    empty_part_with_more = sample_chains["empty_part_with_more"]
    chains = [empty, hello, empty_part, empty_part_with_more]
    print(chains)
    data = b"".join([bc.serialise() for bc in chains])
    reader = ChainReader(
        max_part_size=1024 * 1024, max_chain_size=1024 * 1024, max_chain_length=10
    )
    back_again = [bc for bc in reader.get_binary_chains(data)]
    assert chains == back_again

    # get the EOT positions
    eot_indexes: List[int] = list()
    for index, char in enumerate(data):
        if char == EOC_ORD:
            eot_indexes.append(index + 1)

    # now with chuncks of data, sizes 1 to 20 bytes
    for chunk_size in range(1, 20):
        chunks = split_into_groups(data, chunk_size)
        print("---------------")
        print(chunks)
        reader = ChainReader(
            max_part_size=1024 * 1024, max_chain_size=1024 * 1024, max_chain_length=10
        )
        back_again: List[BinaryChain] = list()
        pos = 0
        for chunk in chunks:
            for bc in reader.get_binary_chains(chunk):
                back_again.append(bc)
            pos += len(chunk)
            assert reader.complete() == (pos in eot_indexes)
        assert chains == back_again


def test_chains_with_large_binary_parts():
    max_size = 2 * 1024 * 1024 * 1024
    for part_length_size, size in BYTE_LENGTHS_MAP:
        if part_length_size > 3:
            break

        print(f"Checking chains with part sizes around {size}")

        chain = BinaryChain(f"{size} - 1", [b"-" * (size - 1)])
        data = chain.serialise()
        part_length_byte = data[len(chain.prefix)]
        assert part_length_byte - ZERO_SOP_ORD == part_length_size
        reader = ChainReader(
            max_part_size=max_size, max_chain_size=max_size, max_chain_length=10
        )
        back = next(reader.get_binary_chains(data))
        assert chain == back

        chain = BinaryChain(f"{size}", [b"=" * size])
        data = chain.serialise()
        part_length_byte = data[len(chain.prefix)]
        assert part_length_byte - ZERO_SOP_ORD == part_length_size
        reader = ChainReader(
            max_part_size=max_size, max_chain_size=max_size, max_chain_length=10
        )
        back = next(reader.get_binary_chains(data))
        assert chain == back

        chain = BinaryChain(f"{size}+1", [b"+" * (size + 1)])
        data = chain.serialise()
        part_length_byte = data[len(chain.prefix)]
        assert part_length_byte - ZERO_SOP_ORD == part_length_size + 1
        reader = ChainReader(
            max_part_size=max_size, max_chain_size=max_size, max_chain_length=10
        )
        back = next(reader.get_binary_chains(data))
        assert chain == back
