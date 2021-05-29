# -*- coding: utf-8 -*-
import argparse
import os
import requests
import sys
import time
import subprocess

from collections import OrderedDict
from lxml import html

WS_URL = 'http://ws.q3df.org'
WS_URL_LIST_TEMPLATE = '{}/maps/?mo=1&show=50&page={{}}'.format(WS_URL)
WS_URL_PK3_TEMPLATE = '{}/maps/downloads/{{}}.pk3'.format(WS_URL)

def collect_pk3_data(pk3_data, final_date=None, final_pk3=None, count=None):

    failure_count = 0
    current_page = 0

    # This variable is a flag for whether or not we have finished collecting pk3 data
    collecting = True

    while(collecting):
        page = requests.get(WS_URL_LIST_TEMPLATE.format(current_page))
        # If we didn't get a 200 response, take a break and try again, if we fail 3 times - die.
        if page.status_code != requests.codes['ok']:
            if failure_count >= 3:
                return 1
            failure_count += 1
            error = "Page returned status code ({}), retrying in 30s".format(page.status_code)
            print(error, file=sys.stderr, flush=True)
            time.sleep(30)
            continue

        tree = html.fromstring(page.content)
        # Grab all the map rows, slice off the header
        maps_table = tree.xpath('//tr')[1:]

        # There can be multiple bsp map files per pk3, so we need to retain
        # state between rows
        pk3_name = None
        pk3_size = None
        release_date = None
        for row in maps_table:
            columns = row.getchildren()

            # End collection condition
            if count and len(pk3_data) >= count:
                collecting = False
                break

            # Each map pk3 name is a link which contains the text, if it's
            # not a link that means this is another map from the previous pk3
            pk3_name_cell = columns[2].find('a')
            if pk3_name_cell is not None:
                pk3_name = pk3_name_cell.text

                # End collection condition
                if final_pk3 and final_pk3 == pk3_name: 
                    collecting = False
                    break

                # The filesize is after some alignment spans
                # [-1] gets the last span spacer within the element
                # strip() removes extra spaces, [:-3] strips the " MB"
                pk3_size = float(columns[3].findall('span')[-1].tail.strip()[:-3])

                # Each one has a 'time' element
                release_date = columns[0].find('time').text

                # End collection condition
                if final_date and release_date < final_date: 
                    collecting = False
                    break

                print("{} collected".format(pk3_name))
                # Initialize the pk3 data structure
                pk3_data[pk3_name] = {}
                pk3_data[pk3_name]['release_date'] = release_date
                pk3_data[pk3_name]['size'] = pk3_size
                pk3_data[pk3_name]['maps'] = []


            # Each map bsp can be taken from the link href
            # [5:-1] strips /map/ and / from the output
            current_map = {}
            current_map['bsp'] = columns[1].find('a').attrib['href'][5:-1]


            # Get the mod name, if there is no 'a', then there is no mod
            mod_cell = columns[4].find('a')
            if mod_cell is not None:
                current_map['mod'] = mod_cell.find('img').attrib['alt']

            # Get the gametypes
            current_map['gametypes'] = [c.attrib['title'] for c in columns[5].findall('a')]

            # TODO columns[6] = weapons
            # TODO columns[7] = items
            # TODO columns[8] = functions

            pk3_data[pk3_name]['maps'].append(current_map)

        # Increment the page number
        current_page += 1

        # Don't DOS pan :)
        time.sleep(2)

    return 0

def process_arguments(argv):
    parser = argparse.ArgumentParser(description="DeFRaG server runner")

    parser.add_argument('-d', '--date',
        metavar='ISO_DATE',
        dest='date',
        help="Stop scraping once we reach this release date (exclusive) formatted in iso 8601 (ex: 2019-01-01)")

    parser.add_argument('-p', '--pk3',
        metavar='PK3_NAME',
        dest='pk3',
        help="Stop scraping once we reach this pk3 name")

    parser.add_argument('-m', '--max',
        metavar='MAX_PK3S',
        dest='max',
        type=int,
        help="Stop scraping once we reach this number of pk3s")

    parser.add_argument('-o', '--output_directory',
        metavar='DIRECTORY_NAME',
        dest='directory',
        required=True,
        help="The directory to save the downloaded pk3s to")


    return parser.parse_args(argv[1:])

def download_pk3s(pk3_data, directory):
    # Create the output directory if it doesn't exist
    if not os.path.exists(directory):
        os.mkdir(directory)

    # Make sure the mountpoint is directory
    if not os.path.isdir(directory):
        print("The file {} is not a directory".format(directory))
        return 1

    for pk3_name in pk3_data.keys():
        url = WS_URL_PK3_TEMPLATE.format(pk3_name)
        output_filename = '{}.pk3'.format(pk3_name)
        path = '{}/{}'.format(directory, output_filename)
        print("Downloading {}...".format(pk3_name), end='', flush=True)

        # In python 3.7 closing() can be removed (and the import too)
#        try:
#            with closing(requests.get(url,
#                         stream=True,
#                         headers={'User-agent': 'defrag-server-scraper'})) as data:
#               data.raise_for_status()
#                with open(path, 'wb') as file_descriptor:
#                    shutil.copyfileobj(data.raw, file_descriptor)

        # Test with wget
        try:
            code = subprocess.call(["wget", url, "--limit-rate=1024k", "--no-check-certificate", "-O", path])
            if code != 0:
                print("Wget returned an ERROR. Aborting!")
                return


            print("DONE!")
        except requests.exceptions.HTTPError:
            print("FAIL!")
            # Although continuing here is an option, returning prevents losing maps to auto dl scripts (with retry)
            return 1
        # Wait a little bit before starting the next file
        time.sleep(1)
    return 0

def main(argv):
    args = process_arguments(argv)

    # Gather the pk3 data from worldspawn
    pk3_data = OrderedDict()
    rc = collect_pk3_data(pk3_data, final_date=args.date, final_pk3=args.pk3, count=args.max)
    if rc != 0:
        return rc

    # Download the pk3s from worldspawn
    return download_pk3s(pk3_data, args.directory)

if __name__ == '__main__':
    sys.exit(main(sys.argv))

# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4