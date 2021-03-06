from tornado import (ioloop, web)

import flou.channel.db as db
import flou.user.pred_db as pred_db
import flou.channel.rss as rss
import flou.channel.imgur as imgur
from flou.utils import Timer
import flou.user.db as user_db

from multiprocessing import Process
import time
import json
import random
from datetime import datetime

import urllib2
import urllib

from pprint import pprint

from bs4 import BeautifulSoup


def fetch_process_method():
    while True:
        # fetch hacker news.
        max_count = 1000
        urls = ['http://hnrss.org/newest',
                'http://www.kurzweilai.net/feed',
                'http://www.engadget.com/rss-full.xml',
                'http://rss.sciam.com/ScientificAmerican-Global',
                'http://www.theverge.com/rss/full.xml',
                'http://www.technologyreview.com/rss/rss.aspx',
                'http://feeds.newscientist.com/science-news',
                'http://venturebeat.com/category/cloud/feed/']
        for url in urls:
            rss.fetch(url, max_count=max_count)
        time.sleep(3600)


fetch_process = Process(target=fetch_process_method)
fetch_process.start()


DAY_CACHE = {}

class FeedHandler(web.RequestHandler):
    def get(self):
        '''
        return all feeds in the database that have images.
        '''
        # filter data sent to client. save bandwidth.
        self.set_header("Access-Control-Allow-Origin", "http://localhost:8100")

        with Timer('feed handler'):
            max_count = 30
            data_whitelist = [
                'content', 'title', 'cover'
            ]

            # get user footprint.
            print '[feed] get feed content'
            userid = self.get_argument('userid')
            print '[feed] userid', userid
            day = datetime.now().strftime('%y.%m.%d.%H')

            # retrive the links already read.
            user_links_read = user_db.get_links_by_user(userid)
            user_links_read = set(user_links_read)
            print '[feed][count] user links read', len(user_links_read)
        
            # retrive latest news contests.
            entries = db.get_all_entries()
            print '[feed] len(entries)', len(entries)
            feeds = []
            feed_by_link = {}
            all_links = set()
            # TODO: modify feed_db so that link is the primary key.
            # do this more efficiently.
            for entry in entries:
                feed = dict(entry)
                link = feed.get('link')
                feed_by_link[link] = feed
                all_links.add(link)

            # generate news recommendation (as links).
            if userid not in DAY_CACHE:
                DAY_CACHE[userid] = {}

            if day in DAY_CACHE[userid]:
                print '[feed][server path] cached'
                recommend_links = DAY_CACHE[userid][day]
            else:
                print '[feed][server path] new'
                preds_sorted = pred_db.get_link_pred_sorted(userid)
                preds_sorted = [(link, pred) for (link, pred) in preds_sorted]
                user_links_sorted = [link for (link, pred) in preds_sorted]
                print '[feed] user links sorted'
                pprint(preds_sorted[:10])
                print '[feed][count] user recommendations', len(user_links_sorted)

                other_links = list(all_links.difference(user_links_sorted))
                random.shuffle(other_links)
                
                recommend_links = [link for link in (user_links_sorted + other_links) if link not in user_links_read]
                recommend_links = recommend_links[:max_count]
                DAY_CACHE[userid][day] = recommend_links

            # retrieve feed content.
            for link in recommend_links:
                if link in feed_by_link and link not in user_links_read:
                    feed = feed_by_link[link]
                    data = feed.get('data')

                    if data:
                        data = json.loads(data)
                        data = {key: data[key] for key in data_whitelist}
                    else:
                        data = {}
                    feed['data'] = json.dumps(data)

                    feeds.append(feed)

            # write back to client.
            print '[feed] writing back', len(feeds), ' feeds'

            self.write({
                'feed': feeds
            })


class SwipeHandler(web.RequestHandler):
    def post(self):
        data = json.loads(self.request.body)
        print 'swipe data', data
        userid = data.get('userid')
        link = data.get('link')
        action = data.get('action')
        print 'link', link
        user_db.add_entry(userid, link, action)
        print 'swipe successful'
        self.write({
            'status': 'OK'
        })


class SummaryHandler(web.RequestHandler):
    def get(self):
        url = self.get_argument('url')

        self.set_header("Access-Control-Allow-Origin", "http://localhost:8100")

        response = urllib2.urlopen('http://www.textteaser.com/summary?%s' % urllib.urlencode({'url': url}))
        soup = BeautifulSoup(response.read(), 'html.parser')
        summaries = []
        for item in soup.find_all('li'):
          summaries.append(item.get_text())

        self.write({
          'summaries': summaries
        })

handlers = [
    # try
    (r"/(.*\.jpg)", web.StaticFileHandler, {"path": "frontend/"}),
    (r"/(.*\.png)", web.StaticFileHandler, {"path": "frontend/"}),
    (r"/(.*\.css)", web.StaticFileHandler, {"path": "frontend/css/"}),
    (r"/(.*\.js)", web.StaticFileHandler, {"path": "frontend/js/"}),
    (r"/vibes/?", FeedHandler),
    (r"/swipe/?", SwipeHandler),
    (r"/summary", SummaryHandler),
]

settings = {
    "autoreload": True,
    "debug": True,
    "template_path": "."
}

if __name__ == "__main__":
    application = web.Application(handlers, **settings)
    application.listen(8889, address="0.0.0.0")
    ioloop.IOLoop.current().start()

