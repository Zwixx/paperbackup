#!/usr/bin/env python

#
# create a pdf with barcodes to backup text files on paper
# designed to backup ascii-armored key files and ciphertext
#

# Copyright 2017 by Intra2net AG, Germany
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
# LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
# WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
#

import os
import logging
import re
import sys
import hashlib
import qrcode
import tempfile
import base64
from io import BytesIO
import argparse
from tempfile import mkstemp
from datetime import datetime
from PIL import Image
from pyx import *
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib.pagesizes import A4, letter
from reportlab.lib.units import cm, inch
from pypdf import PdfReader, PdfWriter

# constants for the size and layout of the barcodes on page
max_bytes_in_barcode = 140
barcodes_per_page = 6
barcode_height = 8
barcode_x_positions = [1.5, 11, 1.5, 11, 1.5, 11]
barcode_y_positions = [18.7, 18.7, 10, 10, 1.2, 1.2]
text_x_offset = 0
text_y_offset = 8.2

plaintext_maxlinechars = 73

# the paperformat to use, activate the one you want
paperformat_obj = document.paperformat.A4
paperformat_str = "A4"
# paperformat_obj=document.paperformat.Letter
# paperformat_str="Letter"


def create_barcode(chunkdata):
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_Q,
        box_size=10,
        border=4,
    )
    qr.add_data(chunkdata)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    # Convert to RGB to avoid warning about single channel image mode
    if img.mode != 'RGB':
        img = img.convert('RGB')
    return img


def finish_page(pdf, canv, pageno):
    canv.text(10, 0.6, "Page %i" % (pageno+1))
    pdf.append(document.page(canv, paperformat=paperformat_obj,
                             fittosize=0, centered=0))


# main code

parser = argparse.ArgumentParser(description='Generate a PDF with barcodes for a given file.')
parser.add_argument('-c', dest='columns', nargs=1, default=[4], type=int,
                    help='number of columns per page (default: 4)')
parser.add_argument('-d', dest='debug', action='store_true',
                    help='debug output')
parser.add_argument('-g', dest='gap', nargs=1, default=[2], type=int,
                    help='minimum gap (%%, default: 2)')
parser.add_argument('-r', dest='rows', nargs=1, default=[5], type=int,
                    help='number of rows per page (default: 5)')
parser.add_argument('-s', dest='paper_size', nargs=1, default=['a4'],
                    help='paper size: a4 or letter (default: a4)')
parser.add_argument('-n', '--no-text', dest='no_text', action='store_true',
                    help='do not include the text/plaintext content in the PDF')
parser.add_argument('input_file', nargs=1,
                    help='file to process (perhaps base64-encoded)')

args = parser.parse_args()

if not args.input_file:
    parser.print_help()
    sys.exit()

input_file = args.input_file[0]

if args.debug:
    logging.basicConfig(level=logging.DEBUG)
else:
    logging.basicConfig(level=logging.CRITICAL)

# constants for the size and layout of the barcodes on page
max_bytes_in_barcode = 140

# page margins
top_margin = 2.2
right_margin = 1.2
left_margin = 1.5
bottom_margin = 1.5

paper_size = args.paper_size[0].lower()

if paper_size == 'a4':
    paperformat_obj = document.paperformat.A4
    paperformat_str = "A4"
    # paper size in cm
    paper_width = 21
    paper_height = 29.7
else:
    paperformat_obj=document.paperformat.Letter
    paperformat_str="Letter"
    # paper size in cm
    paper_width = 21.6
    paper_height = 27.9

logging.info('Paper size: {0}'.format(paper_size))

# number of barcode rows/columns per page (4/5 by default)
barcode_cols = args.columns[0]
barcode_rows = args.rows[0]

cell_width = (paper_width - left_margin - right_margin) / barcode_cols
cell_height = (paper_height - top_margin - bottom_margin) / barcode_rows

# fix "X"
logging.info('Cell dimensions: {0:.2f}×{1:.2f} cm'.format(cell_width, cell_height))

gap_perc = args.gap[0]

if cell_width <= cell_height:
    horizontal_gap = gap_perc * cell_width / 100
    barcode_height = cell_width - horizontal_gap
    vertical_gap = cell_height - barcode_height
else:
    vertical_gap = gap_perc * cell_height / 100
    barcode_height = cell_height - vertical_gap
    horizontal_gap = cell_width - barcode_height

logging.info('Horizontal gap: {0:.2f} cm'.format(horizontal_gap))
logging.info('Vertical gap: {0:.2f} cm'.format(vertical_gap))
logging.info('Barcode height/width: {0:.2f} cm'.format(barcode_height))


barcode_x_positions = [left_margin + (x * (horizontal_gap + barcode_height)) for x in range(barcode_cols)] * barcode_rows
barcode_y_positions = list()
[barcode_y_positions.extend(barcode_cols * [bottom_margin + (x * (vertical_gap + barcode_height))]) for x in range(barcode_rows)]
barcode_y_positions.reverse()
barcodes_per_page = barcode_rows * barcode_cols
text_x_offset = 0
text_y_offset = barcode_height + 0.2
logging.info('Barcode x positions: {0}'.format(barcode_x_positions))
logging.info('Barcode y positions: {0}'.format(barcode_y_positions))

# align to top margin
content_top = max(barcode_y_positions) + text_y_offset
header_content_gap = paper_height - top_margin - content_top
barcode_y_positions = [x + header_content_gap for x in barcode_y_positions]

plaintext_maxlinechars = 73

if not os.path.isfile(input_file):
    raise RuntimeError('File {} not found'.format(input_file))
just_filename = os.path.basename(input_file)

# read file as binary to avoid encoding issues
with open(just_filename, 'rb') as inputfile:
    ascdata_bytes = inputfile.read()

# encode the entire input data to base64 for universal compatibility
# this allows any character/binary data to be stored
ascdata_b64 = base64.b64encode(ascdata_bytes).decode('ascii')

# split the base64 encoded data into chunks of max_bytes_in_barcode size
# each chunk begins with ^<sequence number><space>
# this allows to easily put them back together in the correct order
barcode_blocks = []
chunkdata = "^1 "
for char in list(ascdata_b64):
    if len(chunkdata)+1 > max_bytes_in_barcode:
        # chunk is full -> create barcode from it
        logging.debug('Creating barcode no {0}'.format(len(barcode_blocks) + 1))
        logging.debug('Chunkdata: {0}'.format(chunkdata))
        barcode_blocks.append(create_barcode(chunkdata))
        chunkdata = "^" + str(len(barcode_blocks)+1) + " "

    chunkdata += char

# handle the last, non filled chunk too
if len(chunkdata) > len(str(len(barcode_blocks))) + 2:
    logging.debug('Creating barcode no {0}'.format(len(barcode_blocks) + 1))
    logging.debug('Chunkdata: {0}'.format(chunkdata))
    barcode_blocks.append(create_barcode(chunkdata))

# init PyX
unit.set(defaultunit="cm")
pdf = document.document()

# place barcodes on pages
pgno = 0   # page number
ppos = 0   # position id on page

if len(just_filename) > 19:
    font_size = text.size.tiny
elif len(just_filename) > 15:
    font_size = text.size.small
elif len(just_filename) > 10:
    font_size = text.size.normal
else:
    font_size = text.size.Large

logging.debug('Font size for QR labels: {0}'.format(font_size.size))

c = canvas.canvas()
for bc in range(len(barcode_blocks)):
    # page full?
    if ppos >= barcodes_per_page:
        finish_page(pdf, c, pgno)
        c = canvas.canvas()
        pgno += 1
        ppos = 0

    c.text(barcode_x_positions[ppos] + text_x_offset,
           barcode_y_positions[ppos] + text_y_offset,
           "%s (%i/%i)" % (text.escapestring(just_filename),
                           bc+1, len(barcode_blocks)),
           [font_size])
    c.insert(bitmap.bitmap(barcode_x_positions[ppos],
                           barcode_y_positions[ppos],
                           barcode_blocks[bc], height=barcode_height))
    ppos += 1

finish_page(pdf, c, pgno)
pgno += 1

# write barcode PDF to temporary file, read into BytesIO, then delete
with tempfile.NamedTemporaryFile(mode='w+b', suffix='.pdf', delete=False) as tmp:
    temp_path = tmp.name

pdf.writetofile(temp_path)

# read the temporary file into BytesIO
with open(temp_path, 'rb') as f:
    barcode_pdf_bytes = BytesIO(f.read())

# delete the temporary file
os.remove(temp_path)

# prepare plain text output
input_file_modification = datetime.fromtimestamp(os.path.getmtime(just_filename)).strftime("%Y-%m-%d %H:%M:%S")

# split lines on plaintext_maxlinechars - ( checksum_size + separator size)
splitat=plaintext_maxlinechars - 8
splitlines=[]
for line in ascdata_b64.splitlines():
    while len(line) > splitat:
        splitlines.append(line[:splitat])
        # add a ^ at the beginning of the broken line to mark the linebreak
        line="^"+line[splitat:]
    splitlines.append(line)

# add checksums to each line
chksumlines=[]
for line in splitlines:
    # remove the linebreak marks for checksumming
    if len(line) > 1 and line[0] == "^":
        sumon=line[1:]
    else:
        sumon=line

    # use the first 6 bytes of MD5 as checksum
    chksum = hashlib.md5(sumon.encode('utf-8')).hexdigest()[:6]

    # add the checksum right-justified to the line
    line+=" "*(splitat-len(line))
    line+=" |"+chksum

    chksumlines.append(line)

# we also want a checksum which the restored file should match
checksum = hashlib.sha256(bytes(ascdata_b64, 'utf8')).hexdigest()

# add some documentation around the plaintest
outlines=[]
coldoc=" "*splitat
coldoc+=" | MD5"
outlines.append(coldoc)
outlines.extend(chksumlines)
outlines.append("")
outlines.append("")
outlines.append("DATA IS BASE64 ENCODED - Decode after restoration!")
outlines.append("")
outlines.append("sha256sum of base64 encoded data:")
outlines.append("%s"%checksum)
outlines += r"""

--
Created with paperbackup.py from https://github.com/intra2net/paperbackup/
Data is stored in base64 encoding for universal compatibility.

To restore, either scan this document into a file or use a webcam
This shell script should restore the content inline

/usr/bin/zbarimg --raw -Sdisable -Sqrcode.enable "$SCANNEDFILE" \
    | sed -e "s/\^/\x0/g" \
    | sort -z -n \
    | sed ':a;N;$!ba;s/\n\x0[0-9]* //g;s/\x0[0-9]* //g;s/\n\x0//g' \
    | base64 -d

# replace 'zbarimg \"$SCANNEDFILE\"' with 'zbarcam' if you have a
# webcam instead of a scanned document

# The output is base64 decoded at the end
# algorithm:
# 1. zbarimg ends each scanned code with a newline
# 2. each barcode content begins with ^<number><space>
# 3. convert that to \0<number><space>, so sort can sort on that
# 4. then remove all \n\0<number><space> so we get the original without \n
# 5. base64 -d decodes the base64 string back to the original data

""".split("\n")

# create plaintext PDF using reportlab if not disabled
if not args.no_text:
    # create plaintext PDF using reportlab instead of enscript
    # convert paperformat string to reportlab pagesize
    pagesize = A4 if paperformat_str == "A4" else letter

    # prepare the canvas with Courier font for monospace output
    text_pdf_bytes = BytesIO()
    c = rl_canvas.Canvas(text_pdf_bytes, pagesize=pagesize)

    # calculate font and margin sizes
    font_name = "Courier"
    font_size = 10
    margin = 0.5 * inch
    page_width, page_height = pagesize
    line_height = font_size * 1.2
    lines_per_page = int((page_height - 2 * margin) / line_height)

    # write the header and content
    header = "%s | %s | Page 1" % (just_filename, input_file_modification)
    page_num = 1
    line_num = 0
    y_position = page_height - margin

    # header on first page
    c.setFont(font_name, font_size - 2)
    c.drawString(margin, y_position, header)
    y_position -= line_height * 1.5

    # write all outline lines
    c.setFont(font_name, font_size)
    for line in outlines:
        if line_num >= lines_per_page:
            # new page
            c.showPage()
            page_num += 1
            header = "%s | %s | Page %d" % (just_filename, input_file_modification, page_num)
            c.setFont(font_name, font_size - 2)
            c.drawString(margin, page_height - margin, header)
            c.setFont(font_name, font_size)
            y_position = page_height - margin - line_height * 1.5
            line_num = 0
        
        c.drawString(margin, y_position, line)
        y_position -= line_height
        line_num += 1

    c.save()

# merge PDFs using pypdf
writer = PdfWriter()

# seek to beginning of BytesIO objects before reading
barcode_pdf_bytes.seek(0)

# read the barcode PDF from BytesIO
reader = PdfReader(barcode_pdf_bytes)
for page in reader.pages:
    writer.add_page(page)

# read the text PDF from BytesIO if it was created
if not args.no_text:
    text_pdf_bytes.seek(0)
    reader = PdfReader(text_pdf_bytes)
    for page in reader.pages:
        writer.add_page(page)

# write the combined PDF
with open(just_filename + ".pdf", "wb") as output_pdf:
    writer.write(output_pdf)

print("Please now verify that the output can be restored by calling:")
print("paperbackup-verify.sh {}.pdf".format(just_filename))
