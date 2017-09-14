from flask import Flask, request
import json
import subprocess
import re
from github import Github
app = Flask(__name__)
import subprocess
import requests
import time
import os

@app.route('/', methods=['POST'])
def handle():
    content = json.loads(request.form["payload"])
    if content["ref"] == "refs/heads/master":
        print "something was pushed to master!"
        subprocess.call("./build-staging")
    elif content["ref"] == "refs/heads/production":
        print "something was pushed to production!"
        subprocess.call("./build-production")
    return "OK."

users_to_obey = ['cscheid', 'codementum']

def post_comment(issue_number, comment):
    g = Github("ieeevisbot", os.environ["IEEEVISBOT_PASS"]) # yeah, i know. the github library breaks with PATs.
    r = g.get_repo("ieee-vgtc/ieeevis.org")
    i = r.get_issue(issue_number)
    i.create_comment(body=comment)

class Help:
    def __init__(self):
        self.re = re.compile(r'ieeevisbot, help.')
    def describe(self):
        return "- help - I will describe what I can do."
    def explain(self, content):
        pass
    def check(self, comment):
        m = self.re.search(comment)
        if not m:
            return False
        return True
    def run(self, content):
        issue_number = content['issue']['number']
        help_commands = ["This is what I know:\n"] + [command.describe() for command in commands]
        post_comment(issue_number, "\n".join(help_commands))
        
class UpdateBranch:
    def __init__(self):
        self.re = re.compile(r'ieeevisbot, update ([a-z]+)')
    def describe(self):
        return "- update <site> - I'll clone the chosen site and update AWS buckets"
    def explain(self, content):
        pass
    def check(self, comment):
        m = self.re.search(comment)
        if not m:
            return False
        self.site = m.group(1)
        if not self.site in ['staging', 'production']:
            return False
        return True
    def run(self, content):
        url = content['issue']['pull_request']['patch_url']
        issue_number = content['issue']['number']
        post_comment(issue_number, "Will build %s" % self.site)
        r = subprocess.call("./build-%s" % self.site)
        if r == 0:
            post_comment("Ok, %s pushed successfully.")
    
class EchoCommentFromIssue:
    def __init__(self):
        self.re = re.compile(r'ieeevisbot, say (.*)$')
    def describe(self):
        return "- say <phrase> - I'll repeat whatever you told me to."
    def check(self, comment):
        m = self.re.search(comment)
        if not m:
            return False
        self.command = m.group(1)
        return True
    def run(self, content):
        issue_no = content['issue']['number']
        print "I want to say %s" % self.command
        post_comment(issue_no, self.command)
    def explain(self, content):
        pass

class PatchBranchFromPRCommand:
    def __init__(self):
        self.re = re.compile(r'ieeevisbot, merge with ([a-z]+)')
    def describe(self):
        return "- merge with <branch> - I will attempt to patch the changes from PR where you commented into the branch you told me to."
    def check(self, comment):
        m = self.re.search(comment)
        if not m:
            return False
        self.branch = m.group(1)
        return True
    def explain(self, content):
        url = content['issue']['pull_request']['patch_url']
        issue_number = content['issue']['number']
        post_comment(issue_number, "Ok. You want me to merge the patch %s into branch %s." % (url, self.branch))
    def run(self, content):
        issue_number = content['issue']['number']
        post_comment(issue_number, "Cloning repo...")
        cmd = "git clone git@github.com:ieee-vgtc/ieeevis.org.git /tmp/ieeevis"
        r = subprocess.call(cmd.split(' '))
        if r != 0:
            post_comment(issue_number, "Sorry.\nCommand `%s` failed.\nGiving up." % cmd)
            subprocess.call("rm -rf /tmp/ieeevis".split(" "))
            return
        # arghhh race conditions?!
        time.sleep(1.0)
        cmd = "sh -c 'cd /tmp/ieeevis; git checkout %s'" % self.branch
        r = subprocess.call(['sh', '-c', "cd /tmp/ieeevis; git checkout %s" % self.branch])
        if r != 0:
            post_comment(issue_number, "Sorry.\nCommand `%s` failed.\nGiving up." % cmd)
            subprocess.call("rm -rf /tmp/ieeevis".split(" "))
            return
        url = content['issue']['pull_request']['patch_url']
        r = requests.get(url)
        f = open("/tmp/patch", "w")
        f.write(r.content)
        f.close()
        # arghhh race conditions?!
        time.sleep(1.0)
        post_comment(issue_number, "Patching branch %s..." % self.branch)
        r = subprocess.call(["sh", "-c", 'cd /tmp/ieeevis; git am /tmp/patch'])
        if r != 0:
            post_comment(issue_number, "Sorry - patching failed. I will not push.")
        else:
            post_comment(issue_number, "Ok. Now pushing to %s." % self.branch)
            # arghhh race conditions?!
            time.sleep(1.0)
            subprocess.call(["sh", "-c", 'cd /tmp/ieeevis; git push origin %s' % self.branch])
        subprocess.call("rm -rf /tmp/ieeevis".split())
        subprocess.call("rm /tmp/patch".split())
        
commands = [PatchBranchFromPRCommand(), EchoCommentFromIssue(), UpdateBranch(), Help()]

@app.route('/issue_comment', methods=['POST'])
def handle_issue_comment():
    content = json.loads(request.form["payload"])
    username = content['comment']['user']['login']
    if not username in users_to_obey:
        print "Will ignore comment"
        return "OK."
    print "Comment body I should listen to:"
    body = content['comment']['body']
    for command in commands:
        if command.check(body):
            command.explain(content)
            command.run(content)
    return "OK."

if __name__ == '__main__':
    app.run(port=1234)
