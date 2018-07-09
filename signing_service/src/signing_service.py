import logging.config
import os


logger = logging.getLogger()
crash_logger = logging.getLogger('crash')


def main():
    while True:
        pass


if __name__ == '__main__':
    logging.config.fileConfig(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'logging.ini'))
    main()
