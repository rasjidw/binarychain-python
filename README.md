# Binary Chains

Binary Chains are a simple but flexible binary container format, primarily meant for sending blocks of binary data over streaming interfaces like sockets. Similar to NetStrings, but for binary data.


## Binary Chain Format

A binary chain consists of a prefix, which is an ascii string (strictly bytes of value 0x00 to 0x7F) plus zero or more binary parts.

Each binary part starts with a SOP byte (0x80 to 0x88), the binary part length (big endian encoded), and then the actual data.

The number of bytes in the binary part length is indicated by the SOP byte.
 * 0x80 indicates 0 bytes - implying that the length of the binary part is 0. In this case there are no binary part length bytes, and the data for that part of the chain is of zero length.
 * 0x81 indicates a 1 byte part length - implying that the length of the binary part is between 1 and 255 bytes.
 * 0x82 indicates a 2 byte part length - implying that the length of the binary part is between 256 (0x0100) and 65535 (0xFFFF) bytes.
 * And so on...

The end of the chain is indicated by the EOC marker (0xFF).

So every part (prefix or binary part) is always terminated by a SOP byte or a EOC byte.

The prefix may be empty, and there may be no parts, in which case the serialisation is just the EOC (0xFF) byte.
