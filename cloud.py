import os
from google.cloud import storage
from threading import Thread

import logging
logger = logging.getLogger(__name__)

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "/home/pi/onionbot-819a387e4e79.json"

BUCKET_NAME = "onionbucket" # NOTE: Hard coded in data file


class Cloud(object):
    """Save image to file"""

    def __init__(self):
        self.threads = []

    def _worker(self, path):

        logger.debug("Initialising upload worker")

        client = storage.Client()
        bucket = client.get_bucket(BUCKET_NAME)

        blob = bucket.blob(path)
        blob.upload_from_filename(path)
        blob.make_public()
        logger.debug("Uploaded to cloud: %s" % (path))
        logger.debug("Blob is publicly accessible at %s" % (blob.public_url))

    def start(self, path):

        logger.debug("Calling start")

        thread = Thread(target=self._worker, args=(path,), daemon=True)
        thread.start()

        self.threads.append(thread)

    def join(self):
        for t in self.threads:
            t.join(timeout=1)
            if t.is_alive():
                logger.info("Slow connection to cloud service...")
                return False
        self.threads = []
        return True

    def quit(self):
        logger.debug("Quitting cloud")
        for t in self.threads:
            t.join(timeout=1)
            if t.is_alive():
                logger.error("Cloud thread failed to quit")


