import sys
from collections import Counter
from mmif import Mmif


def print_statistics(fname):
    print(fname)
    for view in Mmif(open(fname).read()).views:
        if 'message' in view.metadata.error:
            status = 'status=ERROR'
        else:
            types = Counter([str(a.at_type).rsplit('/', 1)[-1]
                             for a in view.annotations])
            anno_count = ' '.join(["%s:%s" % (t,c) for t, c in types.items()])
            status = 'status=OKAY - %d annotations (%s)' % (len(view.annotations), anno_count)
        app = view.metadata.app
        if app.startswith('http://mmif.clams.ai/apps/'):
            app = app[26:]
        if app.startswith('https://apps.clams.ai/'):
            app = app[22:]
        print('    %s app=%s %s'
              % (view.id, app, status))


if __name__ == '__main__':

    for fname in sys.argv[1:]:
        print_statistics(fname)
        
