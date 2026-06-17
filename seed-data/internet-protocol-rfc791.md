# The Internet Protocol (IPv4)

A factual reference summary of the Internet Protocol as specified in
**RFC 791** (September 1981). RFC 791 is freely distributable; the field
definitions below are technical facts restated for demonstration purposes.

## Overview

The Internet Protocol (IP) provides for transmitting blocks of data called
**datagrams** from sources to destinations, where sources and destinations are
hosts identified by fixed-length addresses. The Internet Protocol also provides
for fragmentation and reassembly of long datagrams, if necessary, for
transmission through networks with small maximum packet sizes.

IP is deliberately limited in scope. It does not provide reliability, flow
control, or sequencing. It is a best-effort, connectionless service: each
datagram is handled independently, and datagrams may arrive out of order, be
duplicated, or be lost. Higher-level protocols such as TCP add reliability on
top of IP.

## The IPv4 header

The IPv4 header is at least 20 octets (bytes) long. Its fields, in order, are:

### Version and IHL

- **Version** (4 bits): the format of the header. For IPv4 this value is 4.
- **IHL — Internet Header Length** (4 bits): the length of the header in
  32-bit words. The minimum valid value is 5, which corresponds to a 20-octet
  header with no options.

### Type of Service

The **Type of Service** (8 bits) field carries an indication of the abstract
parameters of the quality of service desired. It lets a host signal
precedence, and trade-offs between low delay, high throughput, and high
reliability. Routers may use these hints to select an actual transmission
service.

### Total Length and identification

- **Total Length** (16 bits): the length of the entire datagram, header and
  data, measured in octets. The maximum length a datagram may have is 65,535
  octets. All hosts must be prepared to accept datagrams of up to 576 octets.
- **Identification** (16 bits): a value assigned by the sender to aid in
  assembling the fragments of a datagram.

### Flags and Fragment Offset

- **Flags** (3 bits): control fragmentation. The **Don't Fragment (DF)** flag,
  when set, forbids fragmentation; the **More Fragments (MF)** flag indicates
  whether more fragments follow.
- **Fragment Offset** (13 bits): indicates where in the datagram this fragment
  belongs, measured in units of 8 octets.

### Time to Live

The **Time to Live (TTL)** field (8 bits) indicates the maximum time the
datagram is allowed to remain in the internet system. In practice each router
that processes the datagram decrements the TTL by one; if the TTL reaches zero
the datagram is discarded. This mechanism prevents packets from circulating
forever in routing loops.

### Protocol and Header Checksum

- **Protocol** (8 bits): indicates the next-level protocol carried in the data
  portion of the datagram. For example, TCP is protocol number 6 and UDP is
  protocol number 17.
- **Header Checksum** (16 bits): a checksum on the header only. Because some
  header fields change (for example, Time to Live), the checksum is recomputed
  and verified at each point the header is processed.

### Addresses and options

- **Source Address** (32 bits) and **Destination Address** (32 bits): the IPv4
  addresses of the sending and receiving hosts.
- **Options** (variable): may carry features such as security labels, record
  route, and timestamps. Options are not required in every datagram.

## Fragmentation and reassembly

When a datagram is larger than a network's maximum transmission unit, IP can
split it into fragments. Each fragment is itself a datagram carrying the same
**Identification** value, an appropriate **Fragment Offset**, and the **More
Fragments** flag where applicable. The destination host uses these fields to
reassemble the original datagram. If any fragment is lost, the entire datagram
cannot be reassembled and is eventually discarded.
