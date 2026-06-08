FROM python:3.11-bookworm

# dependencies
RUN apt update && apt-get install -y --no-install-recommends \
        libqrencode-dev enscript ghostscript zbar-tools texlive poppler-utils
RUN pip3 install qrcode pillow pyx reportlab pypdf

# paperbackup
RUN git clone https://github.com/zwixx/paperbackup.git

ENTRYPOINT ["/paperbackup/paperbackup.py"]
