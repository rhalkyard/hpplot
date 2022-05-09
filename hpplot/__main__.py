import argparse
import os
import re
import serial
import time
from typing import AnyStr, Iterable, List, Union


CHAR_ENQ = b'\x05'
CHAR_ACK = b'\x06'


def escape_seq(operation: AnyStr, *args: List[Union[int, AnyStr]]):
    """Generate an interface-control escape sequence of the format:
        ESC . <operation> [ [ <arg> ] [ ; [ <arg> ] ]... : ]

        Arguments may be integers, or single characters whose decimal ASCII
        value will be sent. A None argument, or an empty string, will leave the
        argument position blank, as allowed by the plotter.
    """
    try:
        operation = operation.encode('ascii')
    except AttributeError:
        pass

    if not args:
        return b'\x1b.' + operation
    else:
        argstrs = []
        for arg in args:
            if not arg:
                argstrs.append(b'')
            elif isinstance(arg, bytes) or isinstance(arg, str):
                argstrs.append(str(ord(arg)).encode('ascii'))
            else:
                argstrs.append(str(int(arg)).encode('ascii'))

        return b'\x1b' + b'.' + operation + b';'.join(argstrs) + b':'


def query_buffer(port: serial.Serial):
    """Query the plotter for available buffer space. Returns number of
    available bytes.
    """
    port.reset_input_buffer()
    port.write(escape_seq('B'))
    return int(port.read_until(serial.CR))  # response is terminated with CR


def draw_progressbar(pos: int, total: int):
    """Draws a progress bar on the terminal"""
    # Leave space for text
    terminal_width = os.get_terminal_size().columns * 2 // 3
    bar_length = terminal_width * pos // total
    print('\rProgress: [' + bar_length * '\u2588' +
          (terminal_width-bar_length) * '\u2591' +
          '] ' + str(pos) + '/' + str(total) + ' bytes sent', end='\r')


def chunks(lst: Iterable, n: int):
    """Yield successive n-sized chunks from lst."""
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('port', help='Serial port that plotter is attached to')
    parser.add_argument('file', help='HPGL file to plot')
    parser.add_argument('-b', '--baud-rate', type=int,
                        default=9600, help='Serial baud rate')
    parser.add_argument('-B', '--block-size', type=int,
                        default=80, help='Flow-control block size')
    parser.add_argument('-f', '--flow-control',
                        choices=['query', 'enqack',
                                 'xonxoff', 'rtscts', 'dsrdtr'],
                        default='query',
                        help='Flow-control mode')
    parser.add_argument('-p', '--no-pen-select', action='store_true',
                        help='Remove pen-select commands from HPGL stream')
    parser.add_argument('-v', '--velocity', type=float,
                        help='Override pen velocity')
    args = parser.parse_args()

    xonxoff = False
    rtscts = False
    dsrdtr = False
    if args.flow_control == 'xonxoff':
        xonxoff = True
    elif args.flow_control == 'rtscts':
        rtscts = True
    elif args.flow_control == 'dsrdtr':
        dsrdtr = True

    port = serial.Serial(port=args.port, baudrate=args.baud_rate, timeout=10,
                         xonxoff=xonxoff, rtscts=rtscts, dsrdtr=dsrdtr)
    with open(args.file, 'rb') as f:
        hpgl = f.read()

    # Strip any escape sequences from the HPGL - they could potentially change
    # flow control and echo parameters to something unexpected
    # Escape sequences are of the format:
    #
    # ESC . <letter> [ [ <digits> ] [ ; [ <digits> ] ]... : ]
    hpgl = re.sub(rb'\x1b\.[a-zA-Z\(\)](\d*[;:])*', b'', hpgl)

    if args.velocity:
        velocity_cmd = 'VS{:.4f};'.format(args.velocity).encode('ascii')

        # Replace any explicit velocity commands with our chosen velocity
        hpgl = re.sub(rb'VS\d+(\.\d+)?;', velocity_cmd,
                      hpgl, flags=re.IGNORECASE)

        # Set velocity after an IN or DF command resets it to default
        hpgl = re.sub(rb'(IN|DF);', rb'\1' + velocity_cmd,
                      hpgl, flags=re.IGNORECASE)

        # Set velocity at the beginning of the HPGL stream, in case the stream
        # contains no VS, IN or DF commands
        hpgl = velocity_cmd + hpgl

    if args.no_pen_select:
        # Strip out any pen-select commands
        hpgl = re.sub(rb'SP\d?;', b'', hpgl, flags=re.IGNORECASE)

    # Sometimes the Arduino will reset when we open the serial port. Give it
    # time to boot, and flush any garbage that it may have sent
    time.sleep(1)
    port.reset_input_buffer()

    # Reset handshaking parameters to defaults (no handshaking)
    port.write(escape_seq('R'))

    # Set up our chosen flow-control mode
    if args.flow_control == 'rtscts' or args.flow_control == 'dsrdtr':
        # Enable hardware flow control
        port.write(escape_seq('@', None, 1))
    elif args.flow_control == 'xonxoff':
        # Handshake mode 2, XON/XOFF, DC3 as XOFF char
        port.write(escape_seq('I', args.block_size, None, None, serial.XOFF))
        # DC1 as XON char
        port.write(escape_seq('N', None, serial.XON))
    elif args.flow_control == 'enqack':
        # Handshake mode 2, ENQ/ACK handshaking
        port.write(escape_seq('I', args.block_size, CHAR_ENQ, CHAR_ACK))

    pos = 0
    try:
        draw_progressbar(pos, len(hpgl))
        for block in chunks(hpgl, args.block_size):
            if args.flow_control == 'enqack':
                # ENQ/ACK flow control - send ENQ (0x05) before block, wait for
                # ACK (0x06) response
                port.write(CHAR_ENQ)
                while port.read(1) != CHAR_ACK:
                    time.sleep(0.1)
            elif args.flow_control == 'query':
                # No flow control - query for available buffer size, only send
                # block once space is available.
                while query_buffer(port) < len(block):
                    time.sleep(0.1)

            port.write(block)
            pos += len(block)

            draw_progressbar(pos, len(hpgl))
    except KeyboardInterrupt:
        print()
        print("Plot cancelled")
        port.reset_output_buffer()
        # Send abort command
        port.write(escape_seq('K'))
        time.sleep(0.1)
        # Store pen, move to 0,0, reset plotter
        if not args.no_pen_select:
            port.write(b';SP0;')
        port.write(b'PU0,0;IN;')
    finally:
        # Reset plotter handshake config
        port.write(escape_seq('R'))
        port.close()
    print()


if __name__ == '__main__':
    main()
