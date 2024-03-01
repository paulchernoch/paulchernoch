from os.path import join, isfile, isdir
from pathlib import Path
import sys
import shutil
import regex as re
import markdown2
from slugify import slugify

from yaml import safe_load, dump
try:
    from yaml import CLoader as Loader, CDumper as Dumper
except ImportError:
    from yaml import Loader, Dumper

'''

This program is a static website generator. It converts a source directory tree containing
markdown files, image and css files into a build directory tree of HTML files using a
yaml file that defines the hierarchy of categories, subcategories and articles.
It uses several configuration files to structure the website.

Configuration files:

  - config.yaml
  - sitemap.yaml

  config.yaml should have these properties:

    build:    path to build directory where output files should be written
    images:   path to source directory containing images.
    styles:   path to source directory containing css style files (and svg files used in styles).
    articles: path to source directory where source markdown files are located.
    sitemap:  path to sitemap.yaml file that structures the articles into a hierarchy.

  sitemap.yaml should have a recursive list of dictionaries with these properties:

   - title: A string for the title of the article or section.
   - sub:   An optional string that is the subtitle for the article or section.
   - named: An optional string for the file name of the source markdown file. 
            If absent, the title is turned into a filename by replacing spaces and 
            punctuation to hyphens and adding ".md" as extension.
   - brief: Optional string synopsis of the article.
   - footer: Optional footer for the article.
   - image: Optional string with css class names from FontAwesome that indicate an icon for use in the TOC.
   - dates: List of strings which are publication and edit dates for the article, in the format yyyy-mm-dd.
   - style: Name of HTML template file to use, defaulting to default-page.html
   - parts: Optional recursive list of dictionaries, which are subsections or articles that belong to this section,
            each having the same properties (title, named, brief, footer, image, dates, style and parts).

Command line for script:

  > python build-website.py action [config.yaml]

  The action may be:

    check: Validate the config.yaml and sitemap.yaml files and 
           list all source markdown files that are missing.
    clean: Delete the previous contents of the build directory.
           This prompts the user before deleting the build directory.
    build: Delete the previous contents of the build directory, 
           then read the source files and generate the new website
           under the build directory. 
           This prompts the user before deleting the build directory.
    force: Cleans and builds without asking the user.

  If no config filename is given, assume config.yaml.

Command to Preview website:

  Assuming the configured build directory is called 'build', to preview the website via a simple webserver on a given localhost port,
  do this:

  > cd build
  > python ../serve.py <port>

'''

def load_config() -> tuple[dict,dict,bool]:
  if len(sys.argv) <= 2:
    config_file = "config.yaml"
  else:
    config_file = sys.argv[2]
  print(f'Loading configuration from file {config_file}')

  with open(config_file, 'r') as file:
    config = safe_load(file)

  valid = is_config_valid(config)

  if not valid:
    return config, {}, False

  sitemap_path = config["sitemap"]
  print(f'Loading sitemap from file {sitemap_path}')
  with open(sitemap_path, 'r') as file:
    sitemap = safe_load(file)

  # Yaml parser may yield a list with a single dict.
  if isinstance(config, list):
    config = config[0]
  if isinstance(sitemap, list):
    sitemap = sitemap[0]

  return config, sitemap, True

# Walk the sitemap hierarchy and supply default values for properties that are missing:
#
#   - title: Is required, so no default is supplied.
#   - sub:   If missing, set to None.
#   - named: If missing, compose a file name from the title by replacing spaces and 
#            punctuation to hyphens and adding ".md" as extension.
#   - brief: If missing, set to None.
#   - footer: If missing, set to None.
#   - image: If missing, set to None.
#   - dates: If array is missing or empty, set created and updated to None.
#            If array has one element, set created and updated to that value.
#            If array has more than one element, set created to the first and updated to the last.
#   - style: If missing, set to "default-page.html".
#   - parts: If missing, set to empty array.
#   - open:  Set the top node to open (True) and all others to closed (False).
#   - ancestors: Create a list of titles for the ancestors of this node, with the first element
#                being Home, the common ancestor.
#   - selected: Set to True for Home and False for all others.
def add_sitemap_defaults(sitemap: dict, ancestors: list[str] = []) -> dict:
  if 'sub' not in sitemap:
    sitemap['sub'] = None
  if 'named' not in sitemap:
    sitemap['named'] = f"{slugify(sitemap['title'])}.md"
  if 'brief' not in sitemap:
    sitemap['brief'] = None  
  if 'footer' not in sitemap:
    sitemap['footer'] = None
  if 'image' not in sitemap:
    sitemap['image'] = None
  if 'dates' not in sitemap:
    sitemap['dates'] = []
  if len(sitemap['dates']) == 0:
    sitemap['created'] = None
    sitemap['updated'] = None
  else:
    sitemap['created'] = sitemap['dates'][0]
    sitemap['updated'] = sitemap['dates'][-1]
  if 'style' not in sitemap:
    sitemap['style'] = "default-page.html"
  if 'parts' not in sitemap:
    sitemap['parts'] = []

  # At the beginning, only the root element is open and selected.
  # When a given page is written out, this shall be adjusted
  # so that all the ancestors of the given page will be open
  # and that page will be selected.
  sitemap['open'] = len(ancestors) == 0
  sitemap['selected'] = len(ancestors) == 0
  sitemap['ancestors'] = ancestors[:]
  
  augmented_ancestors = ancestors[:]
  augmented_ancestors.append(sitemap['title'])
  # Recursively set defaults for all contained subcategories and articles.
  for part in sitemap['parts']:
    add_sitemap_defaults(part, augmented_ancestors)

  return sitemap

# Recursively search the tree for the node that has the given title.
def find_node(sitemap: dict, title: str) -> dict | None:
  if sitemap['title'] == title:
    return sitemap
  for part in sitemap['parts']:
    node = find_node(part, title)
    if node is not None:
      return node
  return None

# Every HTML page that is generated will have the same table of contents, but have
# a different state of selection. 
#   - All ancestors (enclosing categories) of the page being written
#     will be open, showing their children.
#   - The page being written will be marked as selected (with a different color).
# This function closes all nodes that are not ancestors or the selected title.
# This function marks as not selected all nodes that are not the title node.
# The originating caller should leave open_titles as None; recursive calls will
# fill in the correct list.
def select_node(sitemap: dict, select_title: str, open_titles: list[str] | None = None):
  if open_titles is None:
    title_node = find_node(sitemap, select_title)
    open_titles = title_node['ancestors'][:]
    open_titles.append(select_title)
    select_node(sitemap, select_title, open_titles)
    return
  
  sitemap['open'] = sitemap['title'] in open_titles
  sitemap['selected'] = sitemap['title'] == select_title
  for part in sitemap['parts']:
    select_node(part, select_title, open_titles)

def is_config_valid(config) -> bool:
  valid = True
  for path_value in ['images', 'styles', 'articles']:
    if not isdir(config[path_value]):
      print(f'Error: Source {path_value} directory does not exist: {config[path_value]}')
      valid = False
  
  if not isfile(config['sitemap']):
    print(f'Error: Source sitemap file does not exist: {config["sitemap"]}')
    valid = False

  return  valid

# Load the article markdown for each title into 'words' and store it in the sitemap.
# Also set the output HTML file path as 'target' 
# and the relative link path for hyper links fro the TOC to 'link'.
def load_articles(config: dict, sitemap: dict, found = {}, missing: list[str] = []) -> tuple[dict,list[str]]:
  source_file = sitemap['named']
  target_file = re.sub("[.]md", ".html", source_file)
  source_path = join(config['articles'], sitemap['named'])
  target_path = join(config['build'], target_file)
  sitemap['target'] = target_path
  sitemap['link'] = target_file

  if not isfile(source_path):
    missing.append(source_path)
    sitemap['found'] = False
    sitemap['words'] = "<p>This article is under construction.</p>"
  else:
    found[sitemap['named']] = source_path
    sitemap['found'] = True
    sitemap['words'] = load_and_convert_article(source_path)

  for part in sitemap['parts']:
    load_articles(config, part, found, missing)
  return found, missing

# Load an article from a file that is in markdown format and convert it to HTML.
def load_and_convert_article(path) -> str:
  with open(path) as f:
    markdown = f.read()
  html = markdown2.markdown(markdown, extras=["metadata"])
  return html

  
def print_with_title(title, body):
  print('-' * len(title))
  print(title)
  print('-' * len(title))
  print(body)

# Validate the inputs and check the existence of article files and paths
def check_action():
  config, sitemap, valid = load_config()
  if not valid:
    return
  print(f'Types of config and sitemap: {type(config)} and {type(sitemap)}')
  print_with_title('Configuration:', dump(config, default_flow_style=False))  
  print_with_title('Sitemap (original):', dump(sitemap, default_flow_style=False, sort_keys=False))
  sitemap = add_sitemap_defaults(sitemap)
  print_with_title('Sitemap (defaults):', dump(sitemap, default_flow_style=False, sort_keys=False))
  found, missing_articles = load_articles(config, sitemap)
  print_with_title("Found article files:", dump(found))

  if len(missing_articles) == 0:
    print_with_title("No Missing article files:", dump(missing_articles))
  else:
    print_with_title("Warning: Missing article files:", dump(missing_articles))

# Remove the target build directory and all files in it.
# This returns the config and sitemap and an indicator of
# whether the build directory was successfully cleaned.
# The indicator is True if the build directory is removed successfully
# OR if there is nothing to remove.
# If there is an error in the configuration, False is returned.
def clear_action(askBeforeDeleting: bool = True) -> tuple[dict,dict,bool]:
  config, sitemap, valid = load_config()
  if not valid:
    print("Error: No directories or files removed because of configuration error(s).")
    return config, sitemap, False

  dir_to_remove = config['build']
  if not isdir(dir_to_remove):
    print(f"Warning: Build directory {dir_to_remove} does not exist, nothing to remove.")
    return config, sitemap, True
  else:
    if askBeforeDeleting:
      answer = input(f"Remove Build directory {dir_to_remove}? (y/n) ")
    else:
      answer = 'y'
    if answer in ['y', 'Y', 'yes', 'Yes', 'YES', 'T', 'True']:
      shutil.rmtree(dir_to_remove) 
      if isdir(dir_to_remove):
        print(f"Warning: Build directory {dir_to_remove} could not be removed.")
        return config, sitemap, False
      else:
        return config, sitemap, True
    else:
      print(f"Warning: Build directory {dir_to_remove} NOT removed.")
      return config, sitemap, False
    
def get_template(page_record: dict, template_cache: dict) -> str:
  template = page_record['style']
  if template in template_cache:
    return template_cache[template]
  else:
    with open(template) as f:
      template_text = f.read()
    template_cache[template] = template_text
    return template_text

# If the value for some macro variables is None, that part of the template should be removed.
# This assumes that the macro is enclosed within a single line by an HTML element like p or div
# that may have an id, class or other properties. This replaces the macro name and its enclosing 
# HTML element by an empty string.
# This also assumes that the macro_name does not contain the dollar signs that wrap it.
def remove_macro(macro_name: str, text: str) -> str:
  regex = f'<[^<$]+\${macro_name}\$<[^>]+>'
  return re.sub(regex, "", text)

def replace_macro(macro_name: str, macro_value: str, text: str) -> str:
  regex = f'\${macro_name}\$'
  return re.sub(regex, macro_value, text)

def build_toc(sitemap: dict, title: str, do_select: bool = True) -> str:
  # If caller has already selected the title, no need to repeat.
  if do_select:
    select_node(sitemap, title)
  return build_toc_helper(sitemap, indent=10)

def toc_link(page_record) -> str:
    title_with_link = f'<a href="{page_record["link"]}">{page_record["title"]}</a>'
    if len(page_record['parts']) == 0:
      if page_record['image'] is not None:
        # Has an icon from FontAwesome
        link = f'<li><i class="{page_record["image"]}"></i> {title_with_link}</li>'
      else:
        # No icon before title
        link = f'<li> {title_with_link}</li>'

    else:
      if page_record['image'] is not None:
        # Has an icon from FontAwesome
        link = f'<i class="{page_record["image"]}"></i> {title_with_link}'
      else:
        # No icon before title
        link = f' {title_with_link}'
    return link

def build_toc_helper(page_record: dict, indent: int) -> str:
  link = toc_link(page_record)
  spaces = ' ' * indent
  if len(page_record['parts']) == 0:
    toc = f'{spaces}{link}\n'
  else:
    # A branch node, with children.
    # Should we mark the details node as open (expanded) or closed (collapsed)?
    if page_record['open']:
      open = ' open=""'
    else:
      open = ''
    toc_parent_before = f'{spaces}<li>\n{spaces}  <details{open}>\n{spaces}    <summary>{link}</summary>\n{spaces}      <ul>\n'
    toc_parent_after  = f'{spaces}      </ul>\n{spaces}  </details>\n{spaces}</li>\n'
    toc_children = ''
    # The indent must exceed the details, summary and ul indentations, so be enlarged more than six. 
    indent += 8
    for part in page_record['parts']:
      toc_child = build_toc_helper(part, indent)
      toc_children += toc_child
    toc = f'{toc_parent_before}{toc_children}{toc_parent_after}'
  return toc

# Substitute values for the macros in the page template.
# These are the macros:
#
#   - $PAGE_TITLE$ will be replaced by the article title
#   - $TOC$ will be replaced by the table of contents
#   - $ARTICLE_TITLE$ will also be replaced by the article title
#   - $ARTICLE_SUBTITLE$ will be replaced by the article subtitle if present, or blanked if not
#   - $ARTICLE_SYNOPSIS$ will be replaced by the article synopsis if present, or blanked if not
#   - $ARTICLE_DATE$ will be replaced by the publication date if present, or blanked if not
#   - $FOOTER$ will be replaced with the article footer if present, or blanked if not
def apply_template(template: str, sitemap: dict, title: str) -> str:
  select_node(sitemap, title)
  page_record = find_node(sitemap, title)
  page = replace_macro("PAGE_TITLE", title, template)

  toc = build_toc(sitemap, title, do_select=False)
  page = replace_macro("TOC", toc, page)

  page = replace_macro("ARTICLE_TITLE", title, page)

  subtitle = page_record['sub']
  if subtitle is None:
    page = remove_macro("ARTICLE_SUBTITLE", page)
  else:
    page = replace_macro("ARTICLE_SUBTITLE", subtitle, page)

  synopsis = page_record['brief']
  if synopsis is None:
    page = remove_macro("ARTICLE_SYNOPSIS", page)
  else:
    page = replace_macro("ARTICLE_SYNOPSIS", synopsis, page)

  page = replace_macro("ARTICLE_BODY", page_record['words'], page)

  create_date = page_record['created']
  update_date = page_record['updated']
  if create_date is None:
    page = remove_macro("ARTICLE_DATE", page)
  elif update_date == create_date:
    create_message = f'Published on {create_date}'
    page = replace_macro("ARTICLE_DATE", create_message, page)
  else:
    update_message = f'Published on {create_date}. Updated on {update_date}.'
    page = replace_macro("ARTICLE_DATE", update_message, page)

  footer = page_record['footer']
  if footer is None:
    page = remove_macro("FOOTER", page)
  else:
    page = replace_macro("FOOTER", footer, page)
  
  return page

# Compose and write all the website pages to the build directory,
# except the index.html and any other static HTML pages for the site.
#
#   1. Recursively walks the sitemap, visiting every title.
#   2. Loads the template for each title.
#   3. Applies the values from the title's definition to the template to generate the HTML.
#   4. Writes the HTML file to the build directory.
#
# As each title is encountered, that title is selected in the larger sitemap by apply_template.
#   - The path down the TOC to the selected title will be rendered as open nodes in the TOC tree.
#   - The selected title will be colored differently.
#
# NOTE: This assumes that the markdown for each title has already been 
#       loaded into the sitemap using load_articles.
def write_articles(config, sitemap, page_record = None, template_cache = {}):
  if page_record is None:
    page_record = sitemap
  select_node(sitemap, page_record['title'])
  template = get_template(page_record, template_cache)
  html = apply_template(template, sitemap, page_record['title'])
  print(f'Writing article {page_record["title"]} to file {page_record["target"]}')
  with open(page_record['target'], 'w') as f:
    f.write(html)

  for part in page_record['parts']:
    write_articles(config, sitemap, part, template_cache)

# Creates the build directories, copies style and image files that are to remain unchanged,
# and generates HTML files for all articles in the sitemap.
def build_action(config, sitemap) -> bool:
  # Create the target build, images and styles directories
  build_dir = config['build']
  images_source_dir = config['images']
  images_build_dir = join(config['build'], 'images')
  styles_source_dir = config['styles']
  styles_build_dir = join(config['build'], 'styles')

  # Make the target build directories
  Path(build_dir).mkdir(parents=True, exist_ok=True)
  Path(images_build_dir).mkdir(parents=True, exist_ok=True)
  Path(styles_build_dir).mkdir(parents=True, exist_ok=True)

  # Copy image and css files
  shutil.copytree(images_source_dir, images_build_dir, dirs_exist_ok=True)
  shutil.copytree(styles_source_dir, styles_build_dir, dirs_exist_ok=True)

  # Copy the index.html landing page
  index_from = "index.html"
  index_to = join(config['build'], index_from)
  if isfile(index_from):
    shutil.copy2(src=index_from, dst=index_to)

  # Copy the 404.html error page
  error_from = "404.html"
  error_to = join(config['build'], error_from)
  if isfile(error_from):
    shutil.copy2(src=error_from, dst=error_to)

  # Load the markdown article source, transform to HTML fragments and attach to the sitemap.
  sitemap = add_sitemap_defaults(sitemap)
  found, missing_articles = load_articles(config, sitemap)

  # Create articles and write them to the build directory.
  write_articles(config, sitemap)
  return True


if __name__ == '__main__':
  action = sys.argv[1] if len(sys.argv) > 1 else "check"
  print(f'Action to perform is {action}')

  if action == "check":
    # Validate configuration and sitemap but neither remove old build nor create new build.
    # Prints more detailed diagnostics.
    check_action()

  elif action in ['clean', 'clear']:
    # Validate configuration and sitemap and remove old build if present; do not create new build.
    # Prompt user before deleting files.
    clear_action(True)

  elif action == 'build':
    # Validate configuration and sitemap and remove old build if present, then create new build.
    # Prompt user before deleting files.
    config, sitemap, is_clear = clear_action(True)
    if is_clear:
      build_action(config, sitemap)

  elif action == 'force':
    # Validate configuration and sitemap and remove old build if present, then create new build.
    # Do not prompt user before deleting files.
    config, sitemap, is_clear = clear_action(False)
    if is_clear:
      build_action(config, sitemap)
    
  else:
    print(f'Action {action} not implemented')

