
# A very simple Flask Hello World app for you to get started with...
# posible bugs:
#          1. parse_story_url(), testString
#          2. delete len(keyword) <=1

from newspaper import Article
from gensim.summarization import summarize, keywords
from gensim.parsing import STOPWORDS, preprocess_string, PorterStemmer
from gensim.models import word2vec
import os
from difflib import SequenceMatcher
from flask import Flask, request, redirect, url_for, render_template
from flask_ask import Ask, statement, question, session
import json
import requests as req
import validators
from random import randint, uniform, gauss
from flask_sqlalchemy import SQLAlchemy
import mechanize
import time
from math import ceil
from time import gmtime, strftime

from set_article_content import set_article_text_not_supported, set_article_text_invalid_url, set_article_text_dulicate, set_article_blank, set_article_404
from parse_story_url import parse_story_url, parse_story_url_to_source_url

from get_string import get_string_database, get_string_facebook

app = Flask(__name__)
ask = Ask(app, "/alexa")

string_database = get_string_database("DATABASE")
SQLALCHEMY_DATABASE_URI = "mysql+mysqlconnector://{username}:{password}@{hostname}/{databasename}".format(
    username=string_database[0],
    password=string_database[1],
    hostname=string_database[2],
    databasename=string_database[3],
)
app.config["SQLALCHEMY_DATABASE_URI"] = SQLALCHEMY_DATABASE_URI
app.config["SQLALCHEMY_POOL_RECYCLE"] = 299
db = SQLAlchemy(app)

from models import *

# Load word2vec models (preload these models at start for repeat use on server)
model_name = "300features_40minwords_10context.gensim"
my_dir = os.path.dirname(__file__)
model_file_path = os.path.join(my_dir, model_name)
model = word2vec.Word2Vec.load(model_file_path)
model_name = "model_400minCount_100dim_10ws.vec"
model_file_path = os.path.join(my_dir, model_name)
model2 = word2vec.Word2Vec.load_word2vec_format(model_file_path)
model_name = "modelSkipgram_100dim_40minCount_10ws.vec"
model_file_path = os.path.join(my_dir, model_name)
model3 = word2vec.Word2Vec.load_word2vec_format(model_file_path)

def similar(a, b):
    return SequenceMatcher(None, a, b).ratio()

def extract_article(story_url):

    article = Article(story_url)
    article.download()
    article.parse()
    title = article.title
    img = article.top_image

    textlen = len(''.join(article.text.encode('ascii','ignore')))
    if not textlen == 0:
        #Adaptive summarize ratio r. <3000:0.3, >3000:0.3*0.7, >6000:0.3*0.7^2, ...
        #r = 0.3*(0.7**(textlen//3000))
        r = min(275, 100*(1.2**(textlen/3000.)))

        summary = summarize(article.text.encode('ascii','ignore'), word_count=int(r))#ratio = r) #split=True, word_count=100, ratio = 0.1
        """
        if type(summary) == 'NoneType':
            return {
                'title':'Sign up for a paid account for free access.',
                'img':img,
                'text': 'Denied Access: to arbitrary websites is not available from free accounts; you can only access sites that are on our whitelist. If you want to suggest something to add to our whitelist ',
                'keywords': 'Denied Access'
        }
        """

        sss = summary.split('\n')
        summary = sss
        count_sentence = 1
        for sentence in summary: # Add number to each sentence (since using ordered list in html encountered indent problems)
            summary[count_sentence-1] = str(count_sentence) + ". " + sentence
            count_sentence = count_sentence + 1

        #summary = summary.replace('\n', ' [|||||]   ') #(legacy)\n is not working in web page => substituting to [|||||]
        kwds = keywords(article.text.encode('ascii','ignore'), ratio=0.05)
        #Clear duplicated words in keywords
        temp = kwds.encode('ascii','ignore').split()

        t_temp = list(temp)
        for ind,i in enumerate(t_temp):
            for j in t_temp[ind+1:len(t_temp)]:
                if similar(i,j)>=0.65 and similar(i,j)<1.0:
                    if j in temp:
                        temp.remove(j)

        ngKeywords = ["needs", "says", "likes", "thinks", "dont", "saying", "come", "said"]
        for kwd in list(temp):
            if not len(kwd)>1:
                temp.remove(kwd)
            else:
                for ngkwd in ngKeywords:
                    if kwd in ngkwd or kwd in STOPWORDS:
                        temp.remove(kwd)
        temp = ', '.join(temp)

        #Return as dictionary type
        return {
            'title':title,
            'img':img,
            #'text':text.encode('ascii','ignore') # only first paragraph will be shown in web page since text is split(\n\n)[0]
            'text': summary,
            'keywords': temp,
            'story_url': story_url,
            'liked_on': 1
        }
    else:
        return None


def read_db_data_to_article(data, *args):
    article = {'title':data.title, 'img': data.imglink, 'text': data.summary.split("[/////]"), 'keywords': data.keywords}
    article['liked_on'] = 1
    article['source_url'] = data.link
    article['id'] = data.id
    if args:
        article['score'] = args[0]
    return article
def ask_read_db_data_to_article(data, *args):
    print "ask_read_db_data_to_article"
    temp = data.summary.replace(". ", "<break time=\"0.5s\"/>")
    temp = temp.split("[/////]")
    temp = [sentence+"<break time=\"1.5s\"/>" for sentence in temp]
    temp = " ".join(temp)
    print data.title.encode('ascii','ignore')
    # 170221: in render_template, all strings should encode('ascii', 'ignore')
    article = {'title':data.title.encode('ascii','ignore'), 'img': data.imglink, 'text': temp.encode('ascii','ignore'), 'domain': data.link.split("/")[2]}
    print "ask_ end"
    article['liked_on'] = 1
    article['source_url'] = data.link
    article['id'] = data.id
    if args:
        article['score'] = args[0]
    return article
def mechanize_login_and_get_html():
    br = mechanize.Browser()
    br.set_handle_robots(False)
    br.open('https://www.facebook.com/login.php')
    br.select_form(nr=0)
    string_facebook = get_string_facebook("FACEBOOK")
    br.form['email'] = string_facebook[0]
    br.form['pass'] = string_facebook[1]
    br.submit()
    time.sleep(1.567)
    res = br.open('https://www.facebook.com/saved/')
    text = res.read()
    br.close()
    return text
def archive_org_save(url):
    br = mechanize.Browser()
    br.set_handle_robots(False)
    testString = "!@?#&;"
    for character in testString:
        url, sep, tail = url.partition(character)
    url = "http://web.archive.org/save/" + url
    br.open(url)
    print "visiting " + url
    time.sleep(20)
    return 0
def parse_fbsaved_html_to_urls(text):
    urls = []
    text = text.replace("\\", "")
    text = text.replace("//", "")
    text = text.replace("https:", "http:")
    text = text.split("&quot;http:") # The start sign of the target url (fb saved link)
    for sentence in text: # extract the target url, which is between the start sign and end sign
        print "--------------------------------------------------"
        if not sentence.startswith("l.facebook") and len(sentence)<=350: # ignore the disturbing "l.facebook"
            index = sentence.find("&quot;)") # end sign of the target url
            sentence = sentence.replace(sentence[index:-1], "") #clear everything after and including "&quot;)"
            if not sentence in urls: #append new url if the processing one is not a duplicate
                urls.append(sentence)
    return urls
def adding_weight_to_dict(idDict, idList, weight):
    for id in idList:
        idDict[id] = idDict.get(id,0) + weight
    return idDict

def searchIndbFacebookSaved(search_value):
    for x in "and or it is the a".split():
        search_value.replace(" "+x+" ","")
    result = dbFacebookSaved.query.filter(dbFacebookSaved.title.ilike("%"+search_value.replace(" ","%")+"%"))#("%" + search_value + "%"))#
    idList = [result.order_by(dbFacebookSaved.date)[count-1].id for count in range(result.count(),0,-1)]
    idDict = dict()
    idDict = adding_weight_to_dict(idDict, idList, 1)
    print ".ilike"
    print idDict

    stemmer = PorterStemmer()
    search_value = search_value.split()
    search_valueRaw = list(search_value)
    if len(search_value)>1:
        sumVector = model3['car']*0
        for searchTerm in search_valueRaw:
            if searchTerm.lower() in model3.vocab:
                sumVector = sumVector + model3[searchTerm.lower()]
        similarList = model3.similar_by_vector(sumVector)
        print "similarList (sumVector)"
        print similarList
        """
        for i in range(min(5,len(similarList))):
                if similarList[i][1] >= 0.7 and similarList[i][0] not in search_value:
                    search_value.append(similarList[i][0])
                    print "append " + similarList[i][0] + " from fasttext(sum of vec)"
        """
        print "New search value after sumVec:"
        search_value += [similarList[i][0] for i in range(min(5,len(similarList))) if similarList[i][1] >= 0.72 and similarList[i][0] not in search_value]
        print search_value

    search_valueR = []
    for searchTerm in search_valueRaw:
        for i,mdl in enumerate([model,model2]):
            if searchTerm.lower() in mdl.vocab:
                similarList = mdl.most_similar(searchTerm.lower())
                listLengh = 3 if i==0 else 5
                scoreThreshold = 0.5 if i==0 else 0.55
                tempText = " from gensim_word2vec for relating to " if i==0 else " from fasttext(CBOW) for relating to "
                for i in range(min(listLengh,len(similarList))):
                    if similarList[i][1] >= scoreThreshold and similarList[i][0] not in search_value:
                        search_value.append(similarList[i][0])
                        search_valueR.append(similarList[i][0])
                        print "append " + similarList[i][0] + tempText + searchTerm
        """
        if searchTerm.lower() in model.vocab:
            similarList = model.most_similar(searchTerm.lower())
            for i in range(min(3,len(similarList))):
                if similarList[i][1] >= 0.5 and similarList[i][0] not in search_value:
                    search_value.append(similarList[i][0])
                    search_valueR.append(similarList[i][0])
                    print "append " + similarList[i][0] + " from gensim_word2vec for relating to " + searchTerm
        if searchTerm.lower() in model2.vocab:
            similarList = model2.most_similar(searchTerm.lower())
            for i in range(min(5,len(similarList))):
                if similarList[i][1] >= 0.55 and similarList[i][0] not in search_value:
                    search_value.append(similarList[i][0])
                    search_valueR.append(similarList[i][0])
                    print "append " + similarList[i][0] + " from fasttext(CBOW) for relating to " + searchTerm
        """
    """
    print "search_value before stemming:"
    print search_value
    stemmer = PorterStemmer()
    search_value = [stemmer.stem(word) for word in search_value]
    search_value = list(set(search_value))
    search_valueR = [stemmer.stem(word) for word in search_valueR]
    search_valueR = list(set(search_valueR))
    print "search_value bafter stemming:"
    """
    print search_value

    for word in search_value:
        if word == stemmer.stem(word) or not stemmer.stem(word) in search_value:
            result = dbFacebookSaved.query.filter(dbFacebookSaved.title.contains(word))
            resultKwd = dbFacebookSaved.query.filter(dbFacebookSaved.keywords.contains(word))
            resultSummary = dbFacebookSaved.query.filter(dbFacebookSaved.summary.contains(word))
            weight = 1
            if len(preprocess_string(word)) == 0:
                weight = 0.1
            elif word in search_valueR:
                weight = 0.5

            idList = [read_db_data_to_article(result.order_by(dbFacebookSaved.date)[count-1])['id'] for count in range(result.count(),0,-1)]
            idDict = adding_weight_to_dict(idDict, idList, 1*weight)
            print ".title.contains(" + word + ")"
            print idDict

            idList = [read_db_data_to_article(resultKwd.order_by(dbFacebookSaved.date)[count-1])['id'] for count in range(resultKwd.count(),0,-1)]
            idDict = adding_weight_to_dict(idDict, idList, 0.5*weight)
            print ".keywords.contains(" + word + ")"
            print idDict

            idList = []
            for count in range(resultSummary.count(),0,-1):
                if not resultSummary.order_by(dbFacebookSaved.date)[count-1].id in idList and len(preprocess_string(word)) > 0:
                    article = read_db_data_to_article(resultSummary.order_by(dbFacebookSaved.date)[count-1])
                    idList.append(article['id'])
                    cumsum = 0
                    # preprocess_string is a gensim function that do preprocessing for a string. ex: people -> peopl, Oranges -> orang
                    word = preprocess_string(word)[0]
                    for w in article['text']:
                        if len(preprocess_string(w)) > 0:
                            w = preprocess_string(w)
                        if cumsum <=0.6 and word in w:
                            idDict[article['id']] = idDict.get(article['id'],0) + 0.2*weight
                            cumsum  = cumsum + 0.2*weight
            print ".summary.contains(" + word + ")"
            #idDict = adding_weight_to_dict(idDict, idList, 0.2)
            print idDict
        else:
            print "ignore " + word + " for " + stemmer.stem(word)
    return idDict
def chooseArticleByWeight(tempList):
    sumScore = 0
    for count, id in tempList:
        sumScore += count
    print "sumScore: " + str(sumScore)
    randNumber = uniform(0, sumScore)
    print "randNumber: " + str(randNumber)
    upper = 0
    resultId = tempList[0][1]
    for count, id in tempList:
        if upper+count >= randNumber:
            resultId = id
            break
        upper += count
    return resultId

@app.route("/")
def index():
    articles = []
    article = {'title':"Please enter your url in the textbox of menubar above.", 'img':'', 'text': {'Recommended sites: theconversation.com, www.scientificamerican.com, www.theguardian.com, spectrum.ieee.org, www.wired.com, backchannel.com',""}, 'keywords': 'English websites only.'}
    article['liked_on'] = 1
    articles.append(article)
    return render_template("index.html", articles=sorted(articles, key=lambda article: article["liked_on"], reverse=True))


@app.route('/', methods=['POST'])
def indexResult():
    articles = []
    story_url = request.form['url']
    source_url = story_url
    #resp = req.head(source_url, allow_redirects=True)
    #story_url = parse_story_url(story_url)
    if validators.url(story_url):
        story_url = parse_story_url(story_url)
    else:
        return redirect(url_for('.errorMessage', message = "invalid", story_url=story_url))

    story_url = json.loads(story_url.text)
    #if 'http://translate.google.com' in source_url:
    #    story_url = source_url

    if 'archived_snapshots' in story_url and story_url['archived_snapshots']:
        story_url = story_url['archived_snapshots'].get('closest',{}).get('url')
    else:
        return redirect(url_for('.errorMessage', message = "notfound", source_url=source_url))

    print "index story_url: " + story_url
    article = extract_article(story_url)
    if not article == None:
        article['source_url'] = source_url
        articles.append(article)
        return render_template("index.html", articles=sorted(articles, key=lambda article: article["liked_on"], reverse=True))
    else:
        return redirect(url_for('.errorMessage', message = "notfound", source_url=source_url))


#codes for chrome extension
@app.route('/chrome-ext/', defaults={'url': ''})
@app.route('/chrome-ext/<path:url>')
def chromeExt(url):
    # From chrome extension we have argument url.
    # To hide the path:url from url bar, we redirect webpage to /chrome-ext/ with a argument 'message' (which is path:url)
    """
    if not url=='':
        return redirect(url_for('.chromeExt', message = url))
    if bool(dict(request.args)): # cast ImmutableMultiDict to dict and to bool(), checking if it is empty
        message = request.args['message']
    else: # If user access /chrome-ext/ directly without argument, redirect to index()
        return redirect(url_for('.index'))
    """

    # 17-01-24 Updated: deprecating <path:url>. Instead use query_string (?chrome_ext_url=...) as input url
    if not bool(request.args.get('chrome_ext_url')):  # If there's no incoming 'chrome_ext_url', redirect to index()
        return redirect(url_for('.index'))
    articles = []
    #story_url = message
    print request.query_string
    story_url = request.args.get('chrome_ext_url') # get some url like "http://..."
    #story_url = url
    story_url = "http://" + story_url # don't replace this line in popup.js: http:// result in http:/
    # source_url will be used for comparing duplication in database later, thus it must be parsed (or the !@#$%^&s will somehow undermine)
    source_url = parse_story_url_to_source_url(story_url)#story_url

    #if the url is valid, parse it, else return invalid page
    if validators.url(story_url):
        story_url = parse_story_url(story_url)
    else:
        return redirect(url_for('.errorMessage', message = "invalid", story_url=story_url))

    story_url = json.loads(story_url.text)

    #if there is a cache page in archive.org, extract the url from the json; else return not supported page
    if 'archived_snapshots' in story_url and story_url['archived_snapshots']:
        story_url = story_url['archived_snapshots'].get('closest',{}).get('url')
    else:
        return redirect(url_for('.errorMessage', message = "notfound", source_url=source_url))

    article = extract_article(story_url)
    if not article == None:
        article['source_url'] = source_url
        articles.append(article)
        return render_template("chrome.html", articles=sorted(articles, key=lambda article: article["liked_on"], reverse=True))
    else:
        return redirect(url_for('.errorMessage', message = "notfound", source_url=source_url))

@app.route('/dbShowArticles/', defaults={'page': 1})
@app.route('/dbShowArticles/page/<int:page>')
def dbShowArticles(page):
    # url_for('function') looks for a function in python
    page_last = dbArticles.query.count()
    perpage = 3
    #dbArticles.select().order_by(dbArticles.id.desc())[page_last-(page-1)*perpage: page_last-page*perpage: -1]
    articles = [read_db_data_to_article(dbSummary.query.order_by(dbSummary.date)[index-1]) for index in range(
        page_last-(page-1)*perpage, page_last-page*perpage, -1) if index <= page_last and index >= 1]
    return render_template("dbShowArticles.html", articles=sorted(articles, key=lambda article: article["liked_on"], reverse=True), ppp=page, p_end=int(ceil(page_last/float(perpage))))



@app.route('/dbShowArticlesRand/')
def dbShowArticlesRand():
    index = randint(1,dbArticles.query.count())
    data = dbSummary.query.filter_by(id=index).first()
    article = read_db_data_to_article(data)
    articles = [article]
    return render_template("dbShowArticles.html", articles=sorted(articles, key=lambda article: article["liked_on"], reverse=True), ppp=1, p_end=1)


@app.route('/dbTS/', defaults={'url': ''})
@app.route('/dbTS/<path:url>')
def dbTextSummarizer(url):
    # Add an article to database

    #MySQL command notes:
    # 1) show tables;
    # 1.1) db name is adArticles for testing
    # 2) describe <db name>;
    # 3) select * from <db name>;
    # 4) Truncate table <db name>;

    # Old method: (1)popup.js: '/dbTS/'+story_url
    #             (2)@app.route('/dbTS/<path:url>') <-this line automatically eliminate '#' and '?' (it only allows '/' in path:url)
    #             (3)story_url = url
    #             (4)comment out: if not bool(...)
    # 17-01-24 Updated: using query_string (?url=... at popup.js) is not good? since multiple '?url='s in input url result bugs
    #                  Sol: rename 'url' as 'chrome_ext_url'

    if not bool(request.args.get('add_db_url')):  # If user access /chrome-ext/ directly without argument, redirect to index()
        return redirect(url_for('.index'))


    articles = []
    story_url = request.args.get('add_db_url')
    #story_url = url
    story_url = "http://" + story_url
    #source_url = story_url
    source_url = parse_story_url_to_source_url(story_url)#story_url
    print "story_url: " + story_url

    #if the url is valid, parse it, else return invalid page
    if validators.url(story_url):
        story_url = parse_story_url(story_url) # stoury_url -> json from archive.org API
    else:
        return redirect(url_for('.errorMessage', message = "invalid", story_url=story_url))

    story_url = json.loads(story_url.text)

    #if there is a cache page in archive.org, extract the url from the json; else return not supported page
    if 'archived_snapshots' in story_url and story_url['archived_snapshots']:
        story_url = story_url['archived_snapshots'].get('closest',{}).get('url')
    else:
        return redirect(url_for('.errorMessage', message = "notfound", source_url=source_url))

    find_duplicate = dbArticles.query.filter_by(link=source_url).first()
    if not find_duplicate:
        article = extract_article(story_url)
        if not article == None:
            article['source_url'] = source_url
            timedate = strftime("%Y-%m-%d %H:%M:%S", gmtime())[0:11]
            articles.append(article)
            dbarticle = dbArticles(title = article['title'], link = article['source_url']) #summary = "".join(article['text'])
            db.session.add(dbarticle)
            db.session.commit()
            dbsummary = dbSummary(title = article['title'], link = article['source_url'], imglink = article['img'], summary = "[/////]".join(article['text']), keywords = article['keywords'], date = timedate)
            db.session.add(dbsummary)
            db.session.commit()
            return redirect(url_for('.dbShowArticles'))
    return redirect(url_for('.errorMessage', message = "duplicate", link=find_duplicate.link, title=find_duplicate.title))

@app.route('/dbFBArticleList/search')
def dbFBSearch():
    # Show search result if request 'search'
    # Input: search_value
    # Process: 1) ilike("%"+search_value.replace(" ","%")+"%")), score+1
    #          2) contains all search terms, +0.5
    #          3) contains any search term in
    #              3.1) title, score+0.5    3.2)keywords, score+0.5     3.3) summary, each appearance+0.2 (max+0.6)
    # Output: return seachResult.html with articles[] ordered by idDict (value = wighted score for each article)
    if not request.args.get('q') == None:
        print "enter if"
        search_value = request.args['q']
        idDict = searchIndbFacebookSaved(search_value)
        tempList = sorted([(count,id) for id,count in idDict.items()],reverse=True)
        print tempList
        articles = [read_db_data_to_article(dbFacebookSaved.query.filter_by(id=index).first(),count) for count,index in tempList if count>0.5]
        articlesLowRelevance = [read_db_data_to_article(dbFacebookSaved.query.filter_by(id=index).first(),count) for count,index in tempList if count<=0.5]
        perpage = 100
        return render_template("searchResult.html", articles=articles, articlesLR=articlesLowRelevance, numResult=len(articles), numResultLR=len(articlesLowRelevance),
        searchTerm=search_value, ppp=1, p_end=int(ceil(len(tempList)/float(perpage))))
    else:
        return redirect(url_for('.dbFBShow', page=1))

@app.route('/dbFBArticleList/', defaults={'page': 1}, methods=['GET'])
@app.route('/dbFBArticleList/<int:page>/', methods=['GET'])
def dbFBShow(page):
    # Show saved pages in dbFacebookSaved database (no need to login facebook)
    # Input: page number (default: 1)
    # Output: return dbFacebookSaved.html which shows 3(perpage=3) articles corresponding to input page
    #articles = []
    page_last = dbFacebookSaved.query.count() # page_last = how many objects in dbFacebookSaved
    perpage = 3 # or 3.0 for float type arithmetic.
    # Show articles for page = page (newest first.)
    # List comprehension
    if request.args.get('hl') == None:
        isHighlight = 0
        articles = [read_db_data_to_article(dbFacebookSaved.query.order_by(dbFacebookSaved.date)[index-1]) for index in range(
            page_last-(page-1)*perpage, page_last-page*perpage, -1) if index <= page_last and index >=1]
    else:
        # Adding html syntax <span class="bg-info"></span> to summary text that highlights the keywords
        isHighlight = 1
        articles = []
        for index in range(page_last-(page-1)*perpage, page_last-page*perpage, -1): #range((page-1)*perpage+1,page*perpage+1):
            if index <= page_last and index >=1:
                #data = dbFacebookSaved.query.filter_by(id=index).first()
                data = dbFacebookSaved.query.order_by(dbFacebookSaved.date)[index-1]
                article = read_db_data_to_article(data)
                for index_s,sentence in enumerate(article['text']):
                    for kwd in article['keywords'].split(", "):
                        if kwd.endswith("s") and not kwd.endswith("ss"):
                            kwd = kwd[:len(kwd)-1]
                        if sentence.lower().find(" "+kwd.lower()) != -1 and len(kwd)>3:
                            temp = article['text'][index_s].lower().find(kwd.lower())
                            article['text'][index_s] = article['text'][index_s][:temp] + "<span class=\"bg-info\">" + article['text'][index_s][temp:temp+len(kwd)] + "</span>" + article['text'][index_s][temp+len(kwd):]
                #print (article['id'], article['title'])
                articles.append(article) # articles.insert(0,article) for reversed order / or use articles.reverse() once for all?
            else:
                article = set_article_blank()
    return render_template("dbFacebookSaved.html", articles=sorted(articles, key=lambda article: article["id"], reverse=True), ppp=page, p_end=int(ceil(page_last/float(perpage))), hl=isHighlight)

@app.route('/urlForArchive/<path:surl>')
def urlForArchive(surl):
    # Input: path surl: www.someurl... (without "http://")
    # Output: redirect to corresponding cached page archive.org/...
    print surl
    surl = "http://" + surl
    print "replace as: " + surl
    story_url = surl
    story_url = parse_story_url(story_url)
    story_url = json.loads(story_url.text)
    story_url = story_url['archived_snapshots'].get('closest',{}).get('url')
    return redirect(story_url)

@app.route('/message/')
def errorMessage():
    if bool(dict(request.args)): # cast ImmutableMultiDict to dict and to bool(), checking if it is empty
        message = request.args['message']
    else: # If user access /chrome-ext/ directly without argument, redirect to index()
        return redirect(url_for('.index'))
    if message == "duplicate":
        articles = []
        title = request.args['title']
        link = request.args['link']
        article = set_article_text_dulicate(title, link)
        articles.append(article)
        return render_template("errorMessage.html", articles=sorted(articles, key=lambda article: article["liked_on"], reverse=True))
    elif message == "invalid":
        articles = []
        story_url = request.args['story_url']
        article = set_article_text_invalid_url(story_url)
        articles.append(article)
        return render_template("errorMessage.html", articles=sorted(articles, key=lambda article: article["liked_on"], reverse=True))
    elif message == "notfound":
        articles = []
        source_url = request.args['source_url']
        article = set_article_text_not_supported(source_url)
        articles.append(article)
        return render_template("errorMessage.html", articles=sorted(articles, key=lambda article: article["liked_on"], reverse=True))
    return render_template("404.html", articles=sorted(articles, key=lambda article: article["liked_on"], reverse=True))

@app.errorhandler(404)
def page_not_found(e):
    articles = []
    articles.append(set_article_404())
    return render_template("404.html", articles=sorted(articles, key=lambda article: article["liked_on"], reverse=True))

@app.route('/gensimTest/')
def gensimTest():
    if not request.args.get('q') == None:
        search_value = request.args['q'].lower()
        if search_value in model.vocab:
            similarList = model.most_similar(search_value)
            print similarList
            text = str(similarList).strip('[]')
        else:
            text = "\"" + search_value + "\" is not in vocabulary of gensim_word2vec model."
        if search_value in model2.vocab:
            similarList = model2.most_similar(search_value)
            print similarList
            text2 = str(similarList).strip('[]')
        else:
            text2 = "\"" + search_value + "\" is not in vocabulary of fasttext model ."
    else:
        text = "No input."
    return "[ " + str(search_value)+" ]<br/>gensim most_similar: <br/>" + text + "<br/><br/>" + "fasttext most_similar: <br/>" + text2


@ask.intent('GetHelloMessage')
def hello():
    text = "Welcom to text summarizer. Want to do some readings on this nice " + strftime("%A") + "?"
    #return statement(text).simple_card('Hello', text)
    return question(text)
@ask.intent('GetAnArticle')
def getAnArticle():
    articleCount = dbFacebookSaved.query.count()
    article = ask_read_db_data_to_article(dbFacebookSaved.query.order_by(dbFacebookSaved.date)[articleCount-1])
    newest_article_msg = render_template("newest_article", title = article['title'], summary = article['text'].encode('ascii','ignore'))
    return statement(newest_article_msg)
@ask.intent('GetRandomArticle')
def getRandArticle():
    articleCount = randint(1,dbFacebookSaved.query.count())
    article = ask_read_db_data_to_article(dbFacebookSaved.query.order_by(dbFacebookSaved.date)[articleCount-1])
    random_article_msg = render_template("random_article", title = article['title'], summary = article['text'].encode('ascii','ignore'), domain = article['domain'])
    return statement(random_article_msg)
@ask.intent('GetArticleWithSearchTerms', mapping={'searchTerm':'SearchTerms'})
def getArticleWithSearchTerms(searchTerm):
    print "intent: GetArticleWithSearchTerms"
    if searchTerm == None:
        return question('Sorry, I didnt get that. What are you looking for?')
    print "searchTerm: " + searchTerm
    idDict = searchIndbFacebookSaved(searchTerm)
    if len(idDict) > 0:
        tempList = sorted([(count,id) for id,count in idDict.items()],reverse=True)
        print tempList
        # Algo. for chosing a relative article: articles with higher counts in idDict have higher chance to be picked
        # randNumber can be considered as an border, once the sumScore (accumulation of count) surpass the border, the corresbonding article id is chosen
        resultId = chooseArticleByWeight(tempList)
        print "resultId: " + str(resultId)
        article = ask_read_db_data_to_article(dbFacebookSaved.query.filter_by(id=resultId).first())
        search_article_msg = render_template("search_article", title = article['title'], summary = article['text'].encode('ascii','ignore'), searchTerm = searchTerm)
        return statement(search_article_msg)
    else:
        return statement('Sorry, I cant find any article in the database for {}'.format(searchTerm))

"""
if __name__ == "__main__":
    db.create_all()
    #app.run()
"""






