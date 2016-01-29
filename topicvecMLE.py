import numpy as np
import scipy.linalg
from scipy.special import *
import getopt
import sys
from utils import *
import pdb
import time
import topicvecUtil

def usage():
    print """topicvecMLE.py [ -v vec_file ... ] doc_file
Options:
  -k:  Number of topic embeddings to extract. Default: 20
  -v:  Existing embedding file of all words.
  -r:  Existing residual file of core words.
  -i:  Number of iterations of the EM procedure. Default: 100
  -u:  Unigram file, to obtain unigram probs.
  -l:  Magnitude of topic embeddings.
"""

K = 20
N0 = 500
max_l = 3
init_l = 1
topD = 12
delta = 0.05
MAX_EM_ITERS = 300
loglike_tolerance = 1e-3
zero_topic1 = True

# V: W x N0
# T: K x N0
# VT: W x K
# u: W x 1
# r: K x 1
# Pi: L x K
# sum_pi_v: K x N0

def calcLoglikelihood( phi, Pi, sum_pi_v, T, r):
    #pdb.set_trace()
    entropy = -np.sum( Pi * np.log(Pi) )
    # Em[k] = sum_j Pi[j][k]
    Em = np.sum( Pi, axis=0 )

    topicvecUtil.fileLogger.debug("Em:")
    topicvecUtil.fileLogger.debug(Em)

    Em_logPhi = Em * np.log(phi)
    sum_r_pi = np.dot( Em, r )
    loglike = entropy + np.sum(Em_logPhi) + np.trace( np.dot( T, sum_pi_v.T ) ) + sum_r_pi
    return loglike

def updatePhi(Pi):
    Em = np.sum( Pi, axis=0 )
    phi = Em / Pi.shape[0]
    return phi

# vocab is for debugging purpose only
def updatePi(phi, T, r, V, wids, vocab):
    L = len(wids)
    K = T.shape[0]
    Pi = np.zeros( (L, K) )

    for i,wid in enumerate(wids):
        v = V[wid]
        Tv = np.dot( T, v )
        Pi[i] = phi * np.exp( Tv + r )

    Pi = normalize(Pi)
    return Pi

def updateTopicEmbeddings(V, u, X, EV, Pi, sum_pi_v, T, r, delta, max_l):
    Em = np.sum( Pi, axis=0 )

    Em_expR = Em * np.exp(r)
    #pdb.set_trace()
    EV_XT = EV + np.dot( T, X  )
    diffMat = sum_pi_v - (EV_XT.T * Em_expR).T
    T2 = T + delta * diffMat

    magT = np.linalg.norm( T, axis=1 )
    magT2 = np.linalg.norm( T2, axis=1 )
    magDiff = np.linalg.norm( delta * diffMat, axis=1 )
    
    tutil.fileLogger.debug( "Magnitudes:" )
    tutil.fileLogger.debug( "T    : %s" %(magT) )
    tutil.fileLogger.debug( "T2   : %s" %(magT2) )
    tutil.fileLogger.debug( "Diff : %s" %(magDiff) )
    
    # max_l == 0: do not do normalization
    if max_l > 0:
        for k in xrange( len(T2) ):
            # do normalization only if the magnitude > max_l
            if np.linalg.norm(T2[k]) > max_l:
                T2[k] = max_l * normalizeF(T2[k])

    if zero_topic1:
        T2[0] = np.zeros(N0)

    r2 = topicvecUtil.calcTopicResiduals(T2, V, u)

    return T2, r2

def main():
    global K, N0, max_l, init_l, topD, delta, MAX_EM_ITERS, loglike_tolerance, zero_topic1

    unigramFilename = "top1grams-wiki.txt"
    vec_file = "25000-500-EM.vec"

    try:
        opts, args = getopt.getopt(sys.argv[1:],"k:v:i:u:l:h")
        if len(args) != 1:
            raise getopt.GetoptError("")
        doc_filename = args[0]
        for opt, arg in opts:
            if opt == '-k':
                K = int(arg)
            if opt == '-v':
                vec_file = arg
            if opt == '-r':
                residual_file = arg
            if opt == '-i':
                MAX_EM_ITERS = int(arg)
            if opt == '-u':
                unigramFilename = arg
            if opt == '-l':
                max_l = int(arg)
            if opt == '-h':
                usage()
                sys.exit(0)

    except getopt.GetoptError:
        usage()
        sys.exit(2)

    vocab_dict = loadUnigramFile(unigramFilename)
    V, vocab, word2ID, skippedWords_whatever = load_embeddings(vec_file)
    # map of word -> id of all words with embeddings
    vocab_dict2 = {}

    # dimensionality of topic/word embeddings
    N0 = V.shape[1]
    # number of all words
    vocab_size = V.shape[0]

    # set unigram probs
    u = np.zeros(vocab_size)

    #pdb.set_trace()

    for wid,w in enumerate(vocab):
        u[wid] = vocab_dict[w][2]
        vocab_dict2[w] = wid

    u = normalize(u)
    vocab_dict = vocab_dict2

    with open(doc_filename) as DOC:
        doc = DOC.readlines()
        doc = "".join(doc)

    wordsInSentences, wc = extractSentenceWords(doc, 2)
    wids = []
    countedWC = 0
    outvocWC = 0
    stopwordWC = 0
    wid2freq = {}
    for sentence in wordsInSentences:
        for w in sentence:
            w = w.lower()
            if w in stopwordDict:
                stopwordWC += 1
                continue

            if w in vocab_dict:
                wid = vocab_dict[w]
                wids.append( wid )
                if wid not in wid2freq:
                    wid2freq[wid] = 1
                else:
                    wid2freq[wid] += 1
                countedWC += 1
            else:
                outvocWC += 1

    print "%d words kept, %d stop words, %d out voc" %( countedWC, stopwordWC, outvocWC )
    wid_freqs = sorted( wid2freq.items(), key=lambda kv: kv[1], reverse=True )
    print "Top words:"
    for wid, freq in wid_freqs[:30]:
        print "%s(%d): %d" %( vocab[wid], wid, freq ),
    print

    T = np.zeros ( (K, N0) )
    for i in xrange(1, K):
        T[i] = np.random.multivariate_normal( np.zeros(N0), np.eye(N0) )
        if init_l > 0:
            T[i] = init_l * normalizeF(T[i])

    if zero_topic1:
        T[0] = np.zeros(N0)
        
    r = topicvecUtil.calcTopicResiduals(T, V, u)
    phi = np.ones(K)
    phi = normalize(phi)
    Pi = updatePi(phi, T, r, V, wids, vocab)
    phi = updatePhi(Pi)

    sum_pi_v = topicvecUtil.calcSum_pi_v(Pi, V, wids)
    loglike = calcLoglikelihood( phi, Pi, sum_pi_v, T, r)
    loglike2 = 0

    print "Precompute Ev and Evv...",

    Ev = np.dot(u, V)
    Evv = np.zeros( (N0, N0) )
    for wid in xrange(vocab_size):
        Evv += u[wid] * np.outer( V[wid], V[wid] )
    #X1 = np.linalg.inv(Evv)
    EV = np.tile( Ev, (K, 1) )

    print "Done."

    it = 0
    print "Iter %d Loglike: %.2f" %(it, loglike)
    topicvecUtil.fileLogger.debug( "Iter %d Loglike: %.2f" %(it, loglike) )

    while it == 0 or ( it < MAX_EM_ITERS and abs(loglike - loglike2) > loglike_tolerance ):
        topicvecUtil.fileLogger.debug( "EM Iter %d:" %it )

        T, r = updateTopicEmbeddings( V, u, Evv, EV, Pi, sum_pi_v, T, r, delta / ( it + 1 ), max_l )
        phi = updatePhi(Pi)
        Pi = updatePi( phi, T, r, V, wids, vocab )
        sum_pi_v = topicvecUtil.calcSum_pi_v( Pi, V, wids )

        loglike2 = loglike
        loglike = calcLoglikelihood( phi, Pi, sum_pi_v, T, r )
        it += 1
        print "Iter %d Loglike: %.2f" %(it, loglike)
        topicvecUtil.fileLogger.debug( "Loglike: %.2f" %loglike )
        
        if it % 5 == 1:
            Em = np.sum( Pi, axis=0 )
            principalK = np.argmax(Em)
            topicvecUtil.fileLogger.debug( "Principal T: %d" %principalK )
    
            topicvecUtil.fileLogger.debug( "T[:,%d]:" %topD )
            topicvecUtil.fileLogger.debug(T[:,:topD])

        if it % 10 == 1:
            topicvecUtil.printTopWordsInTopic( wids, vocab, Pi, V, T, wid2freq, False, topD )

    topicvecUtil.printTopWordsInTopic( wids, vocab, Pi, V, T, wid2freq, True, topD )

    topicvecUtil.fileLogger.debug( "End at %s" %time.ctime() )

if __name__ == '__main__':
    np.seterr(all="raise")
    np.set_printoptions(threshold=np.nan)
    topicvecUtil.fileLogger = initFileLogger( __file__ )
    topicvecUtil.fileLogger.debug( "Begin at %s" %time.ctime() )
    main()