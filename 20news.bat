python topicExp.py -s 20news train
python topicExp.py -i 20news-train-11314-sep281-em150-best.topic.vec 20news train,test
python classEval.py 20news topicprop
python classEval.py 20news topic-wvavg
