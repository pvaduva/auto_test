import urllib.request
import os

import logging


def download_file(url, file_name):
    """Downloading a file from the given url to the given path

    :param url: The url that will be used to download the file
    :param file_name: The complete path including the file name of the downloaded file
    :return: A boolean type indicating the status of the download result
    """
    file_name = os.path.realpath(os.path.expanduser(file_name))
    logging.info('downloading file from {} to {}'.format(url, file_name))

    def get_progress(count, block_size, total_size):
        """Print the download progress

        :param count: Number of block count
        :param block_size: The size of each block
        :param total_size: Total size
        :return:
        """
        percent = int(count * block_size * 100 / total_size)
        progress_bar = '[{}{}] {}%        '.format(int(percent / 5) * '>',
                                                   int(20 - percent / 5) * '-', percent)
        print('\r {}'.format(progress_bar), end='')

    for index in range(0, 10):
        # workaround for url temporarily unavailable
        # to change it back, remove the for loop and change the continue to return False
        try:
            print('Downloading {}'.format(file_name))
            urllib.request.urlretrieve(url, file_name, reporthook=get_progress)
            print()
            print('download finished')
            return True
        except IOError:
            print()
            print('something went wrong when downloading file from {} to {} for the {}th time'
                  .format(url, file_name, index))
            logging.info('something went wrong when downloading file from {} to {}'.
                         format(url, file_name))
            continue
            # return False
    return False
