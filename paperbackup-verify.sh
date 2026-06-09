#!/usr/bin/bash

# USAGE: paperbackup-verify.sh backup.pdf [--password PASSWORD]
#   where backup.pdf should be the pdf created with paperbackup.py
#   --password PASSWORD: provide password for encrypted backup

RESTOREPROG=$(dirname $0)/paperrestore.sh
PASSWORD=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --password)
            PASSWORD="$2"
            shift 2
            ;;
        *)
            PDF_FILE="$1"
            shift
            ;;
    esac
done

if [ -z "$PDF_FILE" ]; then
    echo "USAGE: paperbackup-verify.sh backup.pdf [--password PASSWORD]"
    exit 1
fi

# Restore with password if provided
if [ -n "$PASSWORD" ]; then
    bPDF=$( $RESTOREPROG "$PDF_FILE" "$PASSWORD" | sha256sum | cut -d ' ' -f 1)
else
    bPDF=$( $RESTOREPROG "$PDF_FILE" | sha256sum | cut -d ' ' -f 1)
fi

# Extract checksum from PDF using simple text extraction
# Look for the SHA256 hash (64 hex characters) near "sha256sum" text
bEmbedded=$(pdftotext "$PDF_FILE" - 2>/dev/null | grep -i "sha256sum" | sed -E 's/.*([a-f0-9]{64}).*/\1/' | head -1)

if [ "x$bPDF" == "x$bEmbedded" ]; then
        echo "restored sha256sum from PDF: " $bPDF
        echo "original sha256sum embedded: " $bEmbedded
    echo "sha256sums MATCH :-)"
    echo
    exit 0
else
    echo "Creating diff:"
    if [ -n "$PASSWORD" ]; then
        $RESTOREPROG "$PDF_FILE" "$PASSWORD" | diff "${PDF_FILE%.*}" -
    else
        $RESTOREPROG "$PDF_FILE" | diff "${PDF_FILE%.*}" -
    fi
    diffret=$?
    echo
    if [ $diffret -ne 0 ]; then
        echo "diff and sha256sums do NOT match!"
        echo "restored sha256sum from PDF: " $bPDF
        echo "original sha256sum embedded: " $bEmbedded
        echo
        exit 11
    else
        echo "diff matches but sha256sum is missing."
        echo "restored sha256sum from PDF: " $bPDF
        echo "original sha256sum embedded: " $bEmbedded
        echo
        exit 1
    fi
fi
