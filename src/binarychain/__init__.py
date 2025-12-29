from __future__ import annotations

from typing import Optional, Any, List, Generator

"""
A binary chain consists of a prefix, which is an ascii string (strictly byte of value 0x7F and under)
plus zero or more binary parts.

Each binary part starts with a SOP byte (0x80 to 0x88), the binary part length (big endian encoded), and then the
actual data.

The number of bytes in the binary part length is indicated by the SOP byte.
0x80 indicates 0 bytes - implying that the length of the binary part is 0.
0x81 indicates 1 byte - implying that the length of the binary part is between 1 and 255 bytes.
0x82 indicates 2 bytes - implying that the length of the binary part is between 256 (0x100) and 65535 (0xFFFF) bytes.
... etc ...

The end of the chain is indicated by the EOC marker (0xFF).

So every part (prefix or binary part) is always terminated by a SOP byte or a EOC byte.

The prefix may be empty, and there may be no parts, in which case the serialisation is just the EOC (0xFF) byte.
"""

# TO-DO
# more comments


ZERO_SOP_ORD = 0x80  # Start of Binary Part - length 0
ZERO_SOP = bytes([ZERO_SOP_ORD])
EOC_ORD = 0xFF  # End of Chain
EOC = bytes([EOC_ORD])


class EndOfChainMarkerCls:
    def __repr__(self) -> str:
        return "<EndOfChainMarker>"


EndOfChainMarker = EndOfChainMarkerCls()


BYTE_LENGTHS_MAP = [
    (1, 255),
    (2, 65535),
    (3, 16777215),
    (4, 4294967295),
    (5, 1099511627775),
    (6, 281474976710655),
    (7, 72057594037927935),
    (8, 18446744073709551615),
]
MAX_LENGTH_SIZE = BYTE_LENGTHS_MAP[-1][0]


def create_part_length(length_of_part: int) -> bytes:
    assert isinstance(length_of_part, int)
    if length_of_part < 0:
        raise ValueError("out of range - part_length must be non-negative")

    if length_of_part == 0:
        return ZERO_SOP

    length = None
    for num_bytes, max_value in BYTE_LENGTHS_MAP:
        if length_of_part <= max_value:
            length = num_bytes
            break
    if length is None:
        raise ValueError("out of range - value too large")
    return bytes([ZERO_SOP_ORD + length]) + length_of_part.to_bytes(length, "big")


class BinaryChain:
    def __init__(self, prefix: str = "", parts: Optional[List[bytes|bytearray]] = None):
        if not prefix.isascii():
            raise ValueError('Prefix must be an ascii string')
        self.prefix = prefix
        self.parts: List[bytes|bytearray] = [] if parts is None else parts

    def serialise(self) -> bytes:
        b_prefix = self.prefix.encode("ascii")
        b_parts: List[bytes|bytearray] = [b_prefix]
        for part in self.parts:
            b_parts.extend([create_part_length(len(part)), part])
        return b"".join(b_parts) + EOC

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, BinaryChain):
            return self.prefix == other.prefix and self.parts == other.parts
        else:
            return False

    def __repr__(self) -> str:
        return f"BinaryChain({repr(self.prefix)}, {repr(self.parts)})"

    def __str__(self) -> str:
        prefix_str = (
            self.prefix if len(self.prefix) <= 100 else self.prefix[:100] + "..."
        )
        parts: List[bytes|bytearray] = list()
        for part in self.parts[:10]:
            if len(part) <= 10:
                parts.append(part)
            else:
                parts.append(part[:10] + b"...")
        if len(self.parts) > 10:
            parts.append(b".....")
        return f"BinaryChain<{repr(prefix_str)}, {repr(parts)}>"


class ParseError(Exception):
    pass


class StreamingChainReader:
    IN_PREFIX = "IN_PREFIX"
    IN_PART_LENGTH = "IN_PART_LENGTH"
    IN_BINARY_PART = "IN_BINARY_PART"

    def __init__(self, max_part_size: int, max_chain_size: Optional[int] = None,
                 max_chain_length: Optional[int] = None, max_prefix_size: Optional[int] = None):
        if max_part_size <= 0:
            raise ValueError("max part size must be positive")
        self.max_part_size = max_part_size
        self.max_chain_size = max_chain_size
        self.max_chain_length = max_chain_length
        self.max_prefix_size = max_prefix_size

        self._state = self.IN_PREFIX
        self._buffer = bytearray()
        self._current_prefix_offset = 0
        self._part_length_size: int|None = None  # None = unknown
        self._binary_part_length: int|None = None  # None = unknown
        self._chain_size = 0
        self._chain_length = -1  # don't count the prefix

    def get_chain_items(self, incoming_data: bytes) -> Generator[str|bytes|bytearray|EndOfChainMarkerCls]:
        if not incoming_data:
            raise ValueError("incoming data must not be empty")

        self._buffer.extend(incoming_data)
        while True:
            part, at_end = self._get_next_part()
            if part is None:
                return
            self._chain_size += len(part)
            self._chain_length += 1
            if self.max_chain_size and self._chain_size > self.max_chain_size:
                raise ParseError("chain size too big")
            if self.max_chain_length and self._chain_length > self.max_chain_length:
                raise ParseError(
                    f"chain too long: length of {self._chain_length} > {self.max_chain_length}"
                )
            yield part
            if at_end:
                yield EndOfChainMarker
                self._chain_size = 0
                self._chain_length = -1  # don't count the prefix

    def complete(self) -> bool:
        return self._state == self.IN_PREFIX and not self._buffer

    def _set_state_and_part_length_size_from_sop(self, sop_byte: int) -> bool:
        if sop_byte == EOC_ORD:
            self._part_length_size = None
            self._state = self.IN_PREFIX
            return True
        elif ZERO_SOP_ORD <= sop_byte <= ZERO_SOP_ORD + MAX_LENGTH_SIZE:
            self._part_length_size = sop_byte - ZERO_SOP_ORD
            if self._part_length_size == 0:
                self._binary_part_length = 0
                self._state = self.IN_BINARY_PART
            else:
                self._state = self.IN_PART_LENGTH
            return False
        else:
            raise ParseError("Invalid start of part byte")

    def _get_next_part(self) -> tuple[None|str|bytes|bytearray, bool]:
        if self._state is self.IN_PREFIX:
            return self._get_prefix()
        elif self._state is self.IN_PART_LENGTH:
            self._read_part_length()  # Note: this can change the self._state
            if self._state is self.IN_BINARY_PART:
                return self._get_binary_part()
            else:
                return None, False
        elif self._state is self.IN_BINARY_PART:
            return self._get_binary_part()
        else:
            raise RuntimeError("Invalid state")

    def _get_prefix(self) -> tuple[str|None, bool]:
        for index in range(self._current_prefix_offset, len(self._buffer)):
            byte = self._buffer[index]
            if self.max_prefix_size is not None and index > self.max_prefix_size:
                raise ParseError("Prefix too long")
            if byte >= ZERO_SOP_ORD:
                prefix = self._buffer[:index].decode("ascii")
                at_end = self._set_state_and_part_length_size_from_sop(byte)
                self._buffer = self._buffer[index + 1 :]
                return prefix, at_end
        return None, False

    def _read_part_length(self) -> None:
        buffer_len = len(self._buffer)
        if not self._part_length_size:
            raise RuntimeError("Invalid call")
        if self._part_length_size <= buffer_len:
            encoded_part_length = self._buffer[: self._part_length_size]
            self._buffer = self._buffer[self._part_length_size :]

            self._state = self.IN_BINARY_PART
            self._binary_part_length = int.from_bytes(encoded_part_length, "big")
            if self._binary_part_length > self.max_part_size:
                raise ParseError("Part length too long")
        return

    def _get_binary_part(self) -> tuple[bytes|bytearray|None, bool]:
        if self._binary_part_length is None:
            raise RuntimeError('Invalid call when binary_part_length is None')
        buffer_len = len(self._buffer)
        # include the SOP / EOC character in the length required
        data_length = self._binary_part_length + 1
        if data_length <= buffer_len:
            binary_part_plus_end = self._buffer[:data_length]
            binary_part, sop_byte = binary_part_plus_end[:-1], binary_part_plus_end[-1]
            at_end = self._set_state_and_part_length_size_from_sop(sop_byte)
            self._buffer = self._buffer[data_length:]
            return binary_part, at_end

        # not enough binary data yet
        if len(self._buffer) > self.max_part_size:
            raise ParseError("Binary part too long")
        return None, False


class ChainReader:
    def __init__(self, max_part_size: int, max_chain_size: int, max_chain_length: int):
        self.max_part_size = max_part_size
        self.max_chain_size = max_chain_size
        self.max_chain_length = max_chain_length

        self.streaming_chain_reader = StreamingChainReader(
            self.max_part_size, max_chain_size, max_chain_length
        )
        self._bc = BinaryChain()

    def get_binary_chains(self, incoming_data: bytes) -> Generator[BinaryChain]:
        for item in self.streaming_chain_reader.get_chain_items(incoming_data):
            if isinstance(item, str):
                self._bc.prefix = item
            elif isinstance(item, bytes) or isinstance(item, bytearray):
                self._bc.parts.append(item)
            elif item is EndOfChainMarker:
                result = self._bc
                self._bc = BinaryChain()
                yield result
            else:
                RuntimeError("Invalid item type")

    def complete(self) -> bool:
        return self.streaming_chain_reader.complete()
