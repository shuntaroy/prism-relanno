# convert brat to conll (tsv) format
# read txt to look up characters
# conll = "O" * len(txt)
# for ent in appearance-sorted entities:
#       conll[ent.span.start:ent.span.end] = B-{ent.tag + ent.attr}, I-{ent.tag + ent.attr}
txt = f.readlines()
