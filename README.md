# `hpplot` - simple tool to send data to an HPGL plotter

This is a quick 'n dirty tool to send an HPGL file to a Hewlett-Packard plotter,
with support for various kinds of flow control, and a couple of useful filters
to make changes to the HPGL stream that is sent.

## Installation

```bash
git clone https://github.com/rhalkyard/hpplot
cd hpplot
pip install .
```

## Usage

To plot a file called `plot.hpgl` to a plotter attached to `/dev/ttyUSB0` at
9600 baud, overriding the pen velocity to 15.5 cm/s:

```bash
hpplot --baud-rate 9600 --velocity 15.5 /dev/ttyUSB0 plot.hpgl
```

On Windows, serial port names such as `COM1` can be used instead.

### Arguments

#### `-b BAUD` / `--baud-rate BAUD`

Set the baud rate used when communicating with the plotter. Default is 9600
baud, the fastest speed supported by the HP 7470A.

#### `-f MODE` / `--flow-control MODE`

Set the flow-control mode used in communication with the plotter. The
appropriate escape sequences will be sent to the plotter to configure it for the
selected mode.

Valid modes are:

* `query` (default) - query plotter for available buffer space before sending
  data

* `dsrdtr` - hardware flow control using DSR control line

* `rtscts` - hardware flow control using RTS control line

* `xonxoff` - software flow control using `XON`/`XOFF` protocol

* `enqack` - software flow control using `ENQ`/`ACK` protocol

Note that `dsrdtr` and `rtscts` flow control require a suitably-wired RS232
cable, connecting pin 20 (DTR) on the plotter to DSR for `dsrdtr`, or to CTS for
`rtscts`.

`xonxoff` flow control requires that the serial adapter's driver supports
`XON`/`XOFF` flow control. Some USB-serial adapters are buggy when operating in
this mode, or simply do not support it!

The `query` and `enqack` flow-control modes are implemented entirely within the
`hpplot` tool itself, and should work on any serial interface. In practice, the
default `query` mode should be fine for all uses, I just implemented the others
out of the sake of curiosity.

See the HP 7470A Interfacing and Programming Manual for details about the
plotter's behavior in each flow control mode.

#### `-B BLOCKSIZE` / `--block-size BLOCKSIZE`

Flow-control block size. This value is interpreted slightly differently based on
the flow control mode - see the HP 7470A Interfacing and Programming Manual for
details. Default is 80 bytes, the default block size used by the HP 7470A. There
shouldn't be much need to change this.

#### `-p` / `--no-pen-select`

Suppress any `SP` commands in the HPGL stream. This is useful when adapting
full-length pens for use in the plotter, as they will cause the mechanism to jam
if a pen-change operation is requested.

#### `-v VELOCITY` / `--velocity VELOCITY`

Set the pen velocity, overriding any `VS` commands in the HPGL stream.

## Compatibility

I have only tested `hpplot` with a 7470A, but it should work with other HP
plotters (and clones) that use HPGL and a similar set of configuration escape
sequences.

## HPGL processing

Note that the `-p`/`--no-pen-select` and `-v`/`--velocity` options cause
`hpplot` to rewrite commands in the HPGL stream. These options assume that each
HPGL command is terminated with `;` - a convention that is usually adhered to,
but not strictly required by all commands. Additionally, substrings of text
printed using the `LB` command may get mis-identifed as commands to rewrite.

The arguments for the `-b`/`--block-size` and `-v`/`--velocity` arguments are
not checked for range, as their valid ranges differ for different plotter
models. Valid block sizes for the 7470A range from 1 to 255 bytes, and pen
speeds from 1 to 38.1 cm/s.
