#!/usr/bin/env python3

import os
import sys
import yaml
import argparse
import gitlab

GITLAB_URL = "https://gitlab-on-premise.com"
TOKEN = "xxx"

def get_args():
    parser = argparse.ArgumentParser(description="Delete registry repository tags in bulk")
    parser.add_argument("-c", "--config", dest="config", required=True,
                        help="config file, yaml format", )
    return parser.parse_args()    

class RegTagCleaner(object):
    def __init__(self, conf, token, gitlab_url):
        self.gl = gitlab.Gitlab(gitlab_url, private_token=TOKEN)
        try:
            with open(conf, "r") as config_f:
                self.conf = yaml.safe_load(config_f)
        except Exception as e:
            print(f"FATAL: wrong format of config file: {e}")
            sys.exit(1)
        if "by_projects" in self.conf and len(self.conf["by_projects"]) > 0:
            self.by_projects()
        if "by_groups" in self.conf and len(self.conf["by_groups"]) > 0:
            self.by_groups()        

    def del_tags(self, gl_project, name_regex, keep_n, older_than, reg_path=None):
        print(f"INFO: processing project={gl_project.name_with_namespace}, " \
              f"registry_path={reg_path}, name_regex={name_regex}, " \
              f"keep_n={keep_n}, older_than={older_than}")
        # name_regex is mandatory
        if not name_regex:
            print(f"ERROR: 'name_regex' is mandatory - project={gl_project.name_with_namespace}, " \
                  f"registry_path={reg_path}, name_regex={name_regex} " \
                  f"keep_n={keep_n}, older_than={older_than}")
            return

        criteria = {}  
        if keep_n:
            criteria["keep_n"] = keep_n
        if older_than:
            criteria["older_than"] = older_than          

        try:
            reg_repos = gl_project.repositories.list(all=True)
        except Exception as e:
            print(f"ERROR: can't get list of repositories for " \
                  f"project={gl_project.name_with_namespace}")
            return

        if reg_path:
            reg_rep = None
            for reg_rep_ in reg_repos:
                if reg_rep_.path == reg_path:
                    reg_rep = reg_rep_
                    break
            try:
                reg_rep.tags.delete_in_bulk(name_regex=name_regex, **criteria)
            except Exception as e:
                print(e)
        else:
            # delete tags in all registries in the project 
            for reg_rep_ in reg_repos:
                try:
                    reg_rep_.tags.delete_in_bulk(name_regex=name_regex, **criteria)
                except Exception as e:
                  print(e) 

    def by_projects(self):
        for project in self.conf["by_projects"]:
            project_name_regex = project["name_regex"] if "name_regex" in project else None
            project_keep_n = project["keep_n"] if "keep_n" in project else None
            project_older_than = project["older_than"] if "older_than" in project else None
            gl_project = self.gl.projects.get(project["project"])
            if "by_registry" in project and len(project["by_registry"]) > 0:
                for registry in project["by_registry"]:
                    name_regex = registry["name_regex"] if "name_regex" in registry else project_name_regex
                    keep_n = registry["keep_n"] if "keep_n" in registry else project_keep_n
                    older_than = registry["older_than"] if "older_than" in registry else project_older_than
                    self.del_tags(gl_project, name_regex, keep_n, older_than, 
                                  reg_path=registry["reg_path"]) 
            else:
                self.del_tags(gl_project, project_name_regex, project_keep_n, 
                              project_older_than)

    def by_groups(self):
        for group in self.conf["by_groups"]:
            gl_group = self.gl.groups.get(group["group"])
            gl_projects = gl_group.projects.list(all=True, include_subgroups=True)
            for gl_project in gl_projects:
                gl_project_ = self.gl.projects.get(gl_project.id)
                self.del_tags(gl_project_, group["name_regex"], group["keep_n"], 
                              group["older_than"])
                
if __name__ == "__main__":
    args = get_args()
    if not os.path.isfile(args.config):
        print(f"FATAL: config file doesn't exist {args.config}")
        sys.exit(1)
    else:
        RegTagCleaner(conf=args.config, token=TOKEN, gitlab_url=GITLAB_URL)