import os
import re
import sys
from subprocess import Popen, PIPE, call
from email.Utils import unquote

__all__ = ["Blob", "Reset", "FileChanges", "Commit", "get_total_commits",
           "FastExportFilter", "FastExportOuput", "FastImportInput"]

class IDs(object):
  def __init__(self):
    self.count = 0
    self.translation = {}

  def new(self):
    self.count += 1
    return self.count

  def record_rename(self, old_id, new_id):
    for id in [old_id, new_id]:
      if id > self.count:
        raise SystemExit("Specified ID, %d, has not been created yet." % id)
    if old_id != new_id:
      self.translation[old_id] = new_id

  def translate(self, old_id):
    if old_id > self.count:
      raise SystemExit("Specified ID, %d, has not been created yet." % old_id)
    if old_id in self.translation:
      return self.translation[old_id]
    else:
      return old_id
ids = IDs()

class GitElement(object):
  def __init__(self):
    self.type = None
    self.dumped = 0

  def dump(self, file):
    raise SystemExit("Unimplemented function: %s.dump()", type(self))

class Blob(GitElement):
  def __init__(self, data):
    GitElement.__init__(self)
    self.type = 'blob'
    self.data = data
    self.id = ids.new()

  def dump(self, file):
    if self.dumped: return
    self.dumped = 1

    file.write('blob\n')
    file.write('mark :%d\n' % self.id)
    file.write('data %d\n%s' % (len(self.data), self.data))
    file.write('\n')

class Reset(GitElement):
  def __init__(self, ref, from_ref = None):
    GitElement.__init__(self)
    self.type = 'reset'
    self.ref = ref
    self.from_ref = from_ref

  def dump(self, file):
    if self.dumped: return
    self.dumped = 1

    file.write('reset %s\n' % self.ref)
    if self.from_ref:
      file.write('from :%d\n' % self.from_ref)
      file.write('\n')

class FileChanges(GitElement):
  def __init__(self, type, filename, mode = None, id = None):
    GitElement.__init__(self)
    self.type = type
    self.filename = filename
    if type == 'M':
      if not mode or not id:
        raise SystemExit("file mode and idnum needed for %s" % filename)
      self.mode = mode
      self.id = id

  def dump(self, file):
    if self.dumped: return
    self.dumped = 1

    if self.type == 'M':
      file.write('M %s :%d %s\n' % (self.mode, self.id, self.filename))
    elif self.type == 'D':
      file.write('D %s\n' % self.filename)
    else:
      raise SystemExit("Unhandled filechange type: %s" % self.type)

class Commit(GitElement):
  def __init__(self, branch,
               author_name,    author_email,    author_date,
               committer_name, committer_email, committer_date,
               message,
               file_changes,
               from_commit = None,
               merge_commits = []):
    GitElement.__init__(self)
    self.type = 'commit'
    self.branch = branch
    self.author_name  = author_name
    self.author_email = author_email
    self.author_date  = author_date
    self.committer_name  = committer_name
    self.committer_email = committer_email
    self.committer_date  = committer_date
    self.message = message
    self.file_changes = file_changes
    self.id = ids.new()
    self.from_commit = from_commit
    self.merge_commits = merge_commits

  def dump(self, file):
    if self.dumped: return
    self.dumped = 1

    file.write('commit %s\n' % self.branch)
    file.write('mark :%d\n' % self.id)
    file.write('author %s <%s> %s\n' % \
                     (self.author_name, self.author_email, self.author_date))
    file.write('committer %s <%s> %s\n' % \
                     (self.committer_name, self.committer_email,
                      self.committer_date))
    file.write('data %d\n%s' % (len(self.message), self.message))
    if self.from_commit:
      file.write('from :%s\n' % self.from_commit)
    for ref in self.merge_commits:
      file.write('merge :%s\n' % ref)
    for change in self.file_changes:
      change.dump(file)
    file.write('\n')

class FastExportFilter(object):
  def __init__(self, 
               tag_callback = None,   commit_callback = None,
               blob_callback = None,  progress_callback = None,
               reset_callback = None, checkpoint_callback = None,
               everything_callback = None):
    self.tag_callback        = tag_callback
    self.blob_callback       = blob_callback
    self.reset_callback      = reset_callback
    self.commit_callback     = commit_callback
    self.progress_callback   = progress_callback
    self.checkpoint_callback = checkpoint_callback
    self.everything_callback = everything_callback

    self.input = None
    self.output = sys.stdout
    self.nextline = ''

  def _advance_nextline(self):
    self.nextline = self.input.readline()

  def _parse_optional_mark(self):
    mark = None
    matches = re.match('mark :(\d+)\n$', self.nextline)
    if matches:
      mark = int(matches.group(1))
      self._advance_nextline()
    return mark

  def _parse_optional_baseref(self, refname):
    baseref = None
    matches = re.match('%s :(\d+)\n' % refname, self.nextline)
    if matches:
      baseref = ids.translate( int(matches.group(1)) )
      self._advance_nextline()
    return baseref

  def _parse_optional_filechange(self):
    filechange = None
    if self.nextline.startswith('M '):
      (mode, idnum, path) = \
        re.match('M (\d+) :(\d+) (.*)\n$', self.nextline).groups()
      idnum = int(idnum)
      if path.startswith('"'):
        path = unquote(path)
      filechange = FileChanges('M', path, mode, idnum)
      self._advance_nextline()
    elif self.nextline.startswith('D '):
      path = self.nextline[2:-1]
      if path.startswith('"'):
        path = unquote(path)
      filechange = FileChanges('D', path)
      self._advance_nextline()
    return filechange

  def _parse_ref_line(self, refname):
    matches = re.match('%s (.*)\n$' % refname, self.nextline)
    if not matches:
      raise SystemExit("Malformed %s line: '%s'" % (refname, self.nextline))
    ref = matches.group(1)
    self._advance_nextline()
    return ref

  def _parse_user(self, usertype):
    (name, email, when) = \
      re.match('%s (.*?) <(.*?)> (.*)\n$' % usertype, self.nextline).groups()
    self._advance_nextline()
    return (name, email, when)

  def _parse_data(self):
    size = int(re.match('data (\d+)\n$', self.nextline).group(1))
    data = self.input.read(size)
    self._advance_nextline()
    return data

  def _parse_blob(self):
    # Parse the Blob
    self._advance_nextline()
    id = self._parse_optional_mark()
    data = self._parse_data()
    if self.nextline == '\n':
      self._advance_nextline()

    # Create the blob
    blob = Blob(data)
    if id:
      ids.record_rename(id, blob.id)

    # Call any user callback to allow them to modify the blob
    if self.blob_callback:
      self.blob_callback(blob)
    if self.everything_callback:
      self.everything_callback('blob', blob)

    # Now print the resulting blob
    blob.dump(self.output)

  def _parse_reset(self):
    # Parse the Reset
    ref = self._parse_ref_line('reset')
    from_ref = self._parse_optional_baseref('from')
    if self.nextline == '\n':
      self._advance_nextline()

    # Create the reset
    reset = Reset(ref, from_ref)

    # Call any user callback to allow them to modify the reset
    if self.reset_callback:
      self.reset_callback(reset)
    if self.everything_callback:
      self.everything_callback('reset', reset)

    # Now print the resulting reset
    reset.dump(self.output)

  def _parse_commit(self):
    # Parse the Commit
    branch = self._parse_ref_line('commit')
    id = self._parse_optional_mark()

    author_name = None
    if self.nextline.startswith('author'):
      (author_name, author_email, author_date) = self._parse_user('author')

    (committer_name, committer_email, committer_date) = \
      self._parse_user('committer')

    if not author_name:
      (author_name, author_email, author_date) = \
        (committer_name, committer_email, committer_date)

    commit_msg = self._parse_data()

    from_commit = self._parse_optional_baseref('from')
    merge_commits = []
    merge_ref = self._parse_optional_baseref('merge')
    while merge_ref:
      merge_commits.append(merge_ref)
      merge_ref = self._parse_optional_baseref('merge')
    
    file_changes = []
    file_change = self._parse_optional_filechange()
    while file_change:
      file_changes.append(file_change)
      file_change = self._parse_optional_filechange()
    if self.nextline == '\n':
      self._advance_nextline()

    # Okay, now we can finally create the Commit object
    commit = Commit(branch,
                    author_name,    author_email,    author_date,
                    committer_name, committer_email, committer_date,
                    commit_msg,
                    file_changes,
                    from_commit,
                    merge_commits)
    if id:
      ids.record_rename(id, commit.id)

    # Call any user callback to allow them to modify the commit
    if self.commit_callback:
      self.commit_callback(commit)
    if self.everything_callback:
      self.everything_callback('commit', commit)

    # Now print the resulting commit to stdout
    commit.dump(self.output)

  def run(self, input_file, output_file):
    self.input = input_file
    if output_file:
      self.output = output_file
    self.nextline = input_file.readline()
    while self.nextline:
      if   self.nextline.startswith('blob'):
        self._parse_blob()
      elif self.nextline.startswith('reset'):
        self._parse_reset()
      elif self.nextline.startswith('commit'):
        self._parse_commit()
      else:
        raise SystemExit("Could not parse line: '%s'" % self.nextline)

def FastExportOutput(source_repo, extra_args = []):
  return Popen(["git", "fast-export", "--all", "--topo-order"] + extra_args,
               stdout = PIPE,
               cwd = source_repo).stdout

def FastImportInput(target_repo, extra_args = []):
  if not os.path.isdir(target_repo):
    os.makedirs(target_repo)
    if call(["git", "init"], cwd = target_repo) != 0:
      raise SystemExit("git init in %s failed!" % target_repo)
  return Popen(["git", "fast-import"] + extra_args,
               stdin = PIPE,
               stderr = PIPE,  # We don't want no stinkin' statistics
               cwd = target_repo).stdin

def get_total_commits(repo):
  p1 = Popen(["git", "rev-list", "--all"], stdout = PIPE, cwd = repo)
  p2 = Popen(["wc", "-l"], stdin = p1.stdout, stdout = PIPE)
  return int(p2.communicate()[0])