from os.path import join, isfile, isdir
from pathlib import Path
import sys
import shutil
import regex as re
import markdown2
from slugify import slugify
from bs4 import BeautifulSoup
from functools import lru_cache

from yaml import safe_load, dump
try:
    from yaml import CLoader as Loader, CDumper as Dumper
except ImportError:
    from yaml import Loader, Dumper

CITATIONS = {}

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
   - footer: Optional footer for the article. If omitted, a search bar will be inserted instead.
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

# Add the metadata found in the markdown file plus the computed wordcount.
def add_metadata(sitemap: dict, html: str):
  sitemap['quote'] = None
  sitemap['wordcount'] = 0
  if hasattr(html, 'metadata'):
    metadata = html.metadata
    if 'quote' in metadata:
      sitemap['quote'] = metadata['quote']
    if 'wordcount' in metadata:
      sitemap['wordcount'] = metadata['wordcount']


# Load the article markdown for each title into 'words' and store it in the sitemap.
# Also set the output HTML file path as 'target' 
# and the relative link path for hyper links fro the TOC to 'link'.
def load_articles(config: dict, sitemap: dict, found = {}, missing: list[str] = []) -> tuple[dict,list[str]]:
  global CITATIONS
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

  get_all_citations(sitemap['words'], sitemap['link'], sitemap['title'], CITATIONS)

  add_metadata(sitemap, sitemap['words'])

  for part in sitemap['parts']:
    load_articles(config, part, found, missing)
  return found, missing

def count_words(html_content) -> int:
  # Parse the HTML content
  soup = BeautifulSoup(html_content, 'html.parser')

  # Extract text from the parsed HTML
  text = soup.get_text()

  # Split the text into words
  words = text.split()

  # Count the number of words
  word_count = len(words)

  # Add the word count to the attached metadata (if there is any)
  if hasattr(html_content, 'metadata'):
    metadata = html_content.metadata
    metadata['wordcount'] = word_count

  return word_count

# Load an article from a file that is in markdown format and convert it to HTML.
# If the markdown has metadata, it will be attached to the returned HTML as the metadata property, a dict.
def load_and_convert_article(path) -> str:
  with open(path) as f:
    markdown = f.read()
  html = markdown2.markdown(markdown, extras=["metadata","tables"])
  count_words(html)
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

def get_scripture_index_template() -> str:
  '''
  Get the template for the scripture reference index.
  Since we only create one page with this template, no need to cache it.
  '''
  template = 'scripture-index-template.html'
  with open(template) as f:
    template_text = f.read()
  return template_text

# If the value for some macro variables is None, that part of the template should be removed.
# This assumes that the macro is enclosed within a single line by an HTML element like p or div
# that may have an id, class or other properties. This replaces the macro name and its enclosing 
# HTML element by an empty string.
# This also assumes that the macro_name does not contain the dollar signs that wrap it.
def remove_macro(macro_name: str, text: str) -> str:
  pattern = f'<[^<$]+[$]{macro_name}[$]<[^>]+>'
  return re.sub(pattern, "", text)

def replace_macro(macro_name: str, macro_value: str, text: str) -> str:
  pattern = f'[$]{macro_name}[$]'
  return re.sub(pattern, macro_value, text)

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
#   - $ARTICLE_WORDCOUNT$ will be replaced by the wordcount if present and more than ten, or blanked if not
#   - $ARTICLE_DATE$ will be replaced by the publication date if present, or blanked if not
#   - $FOOTER$ will be replaced with the article footer if present, or a searchbar if not
#   - $QUOTE$ will be replaced by a pull quote if present, or blanked if not
def apply_template(template: str, sitemap: dict, title: str) -> str:
  select_node(sitemap, title)
  page_record = find_node(sitemap, title)
  page = replace_macro("PAGE_TITLE", title, template)

  toc = build_toc(sitemap, title, do_select=False)
  page = replace_macro("TOC", toc, page)

  page = replace_macro("ARTICLE_TITLE", title, page)

  quote = page_record['quote']
  if quote is None:
    page = remove_macro("QUOTE", page)
  else:
    page = replace_macro("QUOTE", quote, page)

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

  wordcount = page_record['wordcount']
  if wordcount <= 10:
    page = remove_macro("ARTICLE_WORDCOUNT", page)
  else:
    wordcount_message = f'{wordcount} words long.'
    page = replace_macro("ARTICLE_WORDCOUNT", wordcount_message, page)

  footer = page_record['footer']
  if footer is None:
    # page = remove_macro("FOOTER", page)
    searchbar = '''
<div id="search"></div>
<script>
    window.addEventListener('DOMContentLoaded', (event) => {
        new PagefindUI({ element: "#search", showSubResults: true });
    });
</script>
<p><a href="scripture-index.html">
  <img src="images/scripture-index-button.png" style="margin-left: 25px;" alt="Scripture Index" height="50px" />
</a></p>
'''
    page = replace_macro("FOOTER", searchbar, page)
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
  scripts_source_dir = config['scripts']
  scripts_build_dir = join(config['build'], 'scripts')

  # Make the target build directories
  Path(build_dir).mkdir(parents=True, exist_ok=True)
  Path(images_build_dir).mkdir(parents=True, exist_ok=True)
  Path(styles_build_dir).mkdir(parents=True, exist_ok=True)
  Path(scripts_build_dir).mkdir(parents=True, exist_ok=True)

  # Copy image, css and script files
  shutil.copytree(images_source_dir, images_build_dir, dirs_exist_ok=True)
  shutil.copytree(styles_source_dir, styles_build_dir, dirs_exist_ok=True)
  shutil.copytree(scripts_source_dir, scripts_build_dir, dirs_exist_ok=True)

  # Copy the index.html landing page
  index_from = "index.html"
  index_to = join(config['build'], index_from)
  if isfile(index_from):
    shutil.copy2(src=index_from, dst=index_to)

  # Copy the quotes.json file for the scriptoquotes
  quotes_from = "quotes.json"
  quotes_to = join(config['build'], quotes_from)
  if isfile(quotes_from):
    shutil.copy2(src=quotes_from, dst=quotes_to)

  # Safety Crytogram Puzzles for work
  puzzles_from = "puzzles.json"
  puzzles_to = join(config['build'], puzzles_from)
  if isfile(puzzles_from):
    shutil.copy2(src=puzzles_from, dst=puzzles_to)

  puzzles_page_from = "puzzles.html"
  puzzles_page_to = join(config['build'], puzzles_page_from)
  if isfile(puzzles_page_from):
    shutil.copy2(src=puzzles_page_from, dst=puzzles_page_to)


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

  # Write out the Scripture index
  index_filename = join(config['build'], f'scripture-index.html')
  write_citations(CITATIONS, index_filename)

  return True

#####################################
#                                   #
#    Index of Bible Citations       #
#                                   #
#####################################

@lru_cache(maxsize=1000)
def get_compiled_pattern(pattern):
    '''
    Reuse regex patterns so that we do not need to create the same regex many times, which is slow.
    '''
    return re.compile(pattern)

def has_citation_for(text: str, book: str, chapter) -> bool:
  '''
  Test if the given text contains a Bible citation for the given book and chapter.
  This does not recognize abbreviations of Bible books.
  '''
  pattern_text = f"{book} ({chapter}|[-0-9,;: ]+[^0-9]{chapter})[^0-9]"
  pattern = get_compiled_pattern(pattern_text)
  match = pattern.search(text)
  return bool(match)

def all_books() -> list[str]:
  return [
    'Genesis',
    'Exodus',
    'Leviticus',
    'Numbers',
    'Deuteronomy',
    'Joshua',
    'Judges',
    'Ruth',
    '1 Samuel',
    '2 Samuel',
    '1 Kings',
    '2 Kings',
    '1 Chronicles',
    '2 Chronicles',
    'Ezra',
    'Nehemiah',
    'Esther',
    'Job',
    'Psalms',
    'Proverbs',
    'Ecclesiastes',
    'Song of Solomon',
    'Isaiah',
    'Jeremiah',
    'Lamentations',
    'Ezekiel',
    'Daniel',
    'Hosea',
    'Joel',
    'Amos',
    'Obadiah',
    'Jonah',
    'Micah',
    'Nahum',
    'Habakkuk',
    'Zephaniah',
    'Haggai',
    'Zechariah',
    'Malachi',
    'Matthew',
    'Mark',
    'Luke',
    'John',
    'Acts',
    'Romans',
    '1 Corinthians',
    '2 Corinthians',
    'Galatians',
    'Ephesians',
    'Philippians',
    'Colossians',
    '1 Thessalonians',
    '2 Thessalonians',
    '1 Timothy',
    '2 Timothy',
    'Titus',
    'Philemon',
    'Hebrews',
    'James',
    '1 Peter',
    '2 Peter',
    '1 John',
    '2 John',
    '3 John',
    'Jude',
    'Revelation'
  ]

def old_testament_books() -> list[str]:
  return [
    'Genesis',
    'Exodus',
    'Leviticus',
    'Numbers',
    'Deuteronomy',
    'Joshua',
    'Judges',
    'Ruth',
    '1 Samuel',
    '2 Samuel',
    '1 Kings',
    '2 Kings',
    '1 Chronicles',
    '2 Chronicles',
    'Ezra',
    'Nehemiah',
    'Esther',
    'Job',
    'Psalms',
    'Proverbs',
    'Ecclesiastes',
    'Song of Solomon',
    'Isaiah',
    'Jeremiah',
    'Lamentations',
    'Ezekiel',
    'Daniel',
    'Hosea',
    'Joel',
    'Amos',
    'Obadiah',
    'Jonah',
    'Micah',
    'Nahum',
    'Habakkuk',
    'Zephaniah',
    'Haggai',
    'Zechariah',
    'Malachi'
  ]

def new_testament_books() -> list[str]:
  return [
    'Matthew',
    'Mark',
    'Luke',
    'John',
    'Acts',
    'Romans',
    '1 Corinthians',
    '2 Corinthians',
    'Galatians',
    'Ephesians',
    'Philippians',
    'Colossians',
    '1 Thessalonians',
    '2 Thessalonians',
    '1 Timothy',
    '2 Timothy',
    'Titus',
    'Philemon',
    'Hebrews',
    'James',
    '1 Peter',
    '2 Peter',
    '1 John',
    '2 John',
    '3 John',
    'Jude',
    'Revelation'
  ]

def book_chapter_counts() -> dict:
  return {
    'Genesis': 50,
    'Exodus': 40,
    'Leviticus': 27,
    'Numbers': 36,
    'Deuteronomy': 34,
    'Joshua': 24,
    'Judges': 21,
    'Ruth': 4,
    '1 Samuel': 31,
    '2 Samuel': 24,
    '1 Kings': 22,
    '2 Kings': 25,
    '1 Chronicles': 29,
    '2 Chronicles': 36,
    'Ezra': 10,
    'Nehemiah': 13,
    'Esther': 10,
    'Job': 42,
    'Psalms': 150,
    'Proverbs': 31,
    'Ecclesiastes': 12,
    'Song of Solomon': 8,
    'Isaiah': 66,
    'Jeremiah': 52,
    'Lamentations': 5,
    'Ezekiel': 48,
    'Daniel': 12,
    'Hosea': 14,
    'Joel': 3,
    'Amos': 9,
    'Obadiah': 1,
    'Jonah': 4,
    'Micah': 7,
    'Nahum': 3,
    'Habakkuk': 3,
    'Zephaniah': 3,
    'Haggai': 2,
    'Zechariah': 14,
    'Malachi': 4,
    'Matthew': 28,
    'Mark': 16,
    'Luke': 24,
    'John': 21,
    'Acts': 28,
    'Romans': 16,
    '1 Corinthians': 16,
    '2 Corinthians': 13,
    'Galatians': 6,
    'Ephesians': 6,
    'Philippians': 4,
    'Colossians': 4,
    '1 Thessalonians': 5,
    '2 Thessalonians': 3,
    '1 Timothy': 6,
    '2 Timothy': 4,
    'Titus': 3,
    'Philemon': 1,
    'Hebrews': 13,
    'James': 5,
    '1 Peter': 5,
    '2 Peter': 3,
    '1 John': 5,
    '2 John': 1,
    '3 John': 1,
    'Jude': 1,
    'Revelation': 22
  }

def get_all_citations(text: str, filename: str, title: str, citations = {}) -> dict:
  '''
  Find all citations to all Bible books in the given text and add them to the 
  collection of citations collected so far.
  The citation will include the file name and the document title for the source text.

  The structure of the data is:
    - first level dict where the key is the name of a Bible book
    - value is a second level dict where the key is an integer chapter number
    - value of the second level dict is a list of citations
    - the citations are third level dicts with the keys 'filename' and 'title'
    - the 'filename' is the name of the HTML file that has the Bible reference
    - the 'title' is the title of the document.

  The filename and title will later be used to make HTML hyperlinks.
  '''
  books = all_books()
  chapters = book_chapter_counts()

  for book in books:
    if book not in citations:
      book_citations = {}
    else:
      book_citations = citations[book]
    
    any_citations_for_book = False
    max_chapter = chapters[book]
    for chapter in range(1,max_chapter+1):
      if has_citation_for(text, book, chapter):
        any_citations_for_book = True
        if chapter not in book_citations:
          book_citations[chapter] = []
        book_chapter_citations = book_citations[chapter]
        book_chapter_citations.append({
          'filename': filename,
          'title': title
        })
    # Only add an entry for a book if there is at least one citation to that book.
    if any_citations_for_book:
      citations[book] = book_citations

  return citations

def citation_page_head():
  template = '''
<!DOCTYPE html>
<head>
  <!--from template: default-page.html -->
  <title>Scripture Index</title>
  <link rel="stylesheet" href="./styles/gryptocram.css" type="text/css">
  <link rel="stylesheet" href="./styles/tree.css" type="text/css">
  <link rel="stylesheet" href="./styles/toc.css" type="text/css">
  <link rel="stylesheet" href="./styles/article.css" type="text/css">
  <!-- Font Awesome supplies the icons used in the TOC -->
  <script src="https://kit.fontawesome.com/ecadd7b212.js" crossorigin="anonymous"></script>
  <link rel="stylesheet" href="./styles/page.css" type="text/css">

</head>
'''
  return template


def format_citations(citations: dict) -> str:
  '''
  Using the old style where Old and New Testament citations were rendered in a single column,
  format citations that were generated by get_all_citations as HTML, with 
  hyperlinks to every document that has a Bible citation.
  This does not use the template file scripture-index-template.html.
  '''
  books = all_books()
  chapters = book_chapter_counts()
  citation_html = citation_page_head()
  citation_html += '''
<html>
<body>
  <div class="citations">
    <h1>Index of Scriptures Referenced</h1>
'''

  # <details class="scripture">
  #     <summary><h2>Book name</h2></summary>
  #     <p>This is the text that will show when you click on the summary text</p>
  # </details>

  for book in books:
    if book in citations:
      citation_html += f'  <details class="citations article">\n'
      citation_html += f'    <summary><h2>{book}</h2></summary>\n'
      citation_html += f'      <p><ul>\n'
      book_citations = citations[book]
      for chapter in range(1,chapters[book]+1):
        if chapter in book_citations:
          book_chapter_citations = book_citations[chapter]
          citation_html += f'        <li>Chapter {chapter}\n        <ul>\n'
          for citation in book_chapter_citations:
            file = citation['filename']
            title = citation['title']
            citation_html += f'            <li><a href="{file}">{title}</a></li>\n'
          citation_html += f'          </ul>\n        </li>\n'
      citation_html += f'      </ul></p>\n'
      citation_html += f'    </summary>\n'
      citation_html += f'  </details>\n'
  citation_html += '</div>\n'
  citation_html += '</body>\n</html>\n'
  return citation_html

def citations_for_one_book(book: str, citations: dict) -> str:
  chapters = book_chapter_counts()
  citation_html = ''
  citation_html += f'  <details class="citations article">\n'
  citation_html += f'    <summary><h2>{book}</h2></summary>\n'
  citation_html += f'      <p><ul>\n'
  book_citations = citations[book]
  for chapter in range(1,chapters[book]+1):
    if chapter in book_citations:
      book_chapter_citations = book_citations[chapter]
      citation_html += f'        <li>Chapter {chapter}\n        <ul>\n'
      for citation in book_chapter_citations:
        file = citation['filename']
        title = citation['title']
        citation_html += f'            <li><a href="{file}">{title}</a></li>\n'
      citation_html += f'          </ul>\n        </li>\n'
  citation_html += f'      </ul></p>\n'
  citation_html += f'    </summary>\n'
  citation_html += f'  </details>\n'
  return citation_html

def format_citations_by_testament(citations: dict) -> str:
  '''
  New style where Old and New Testament citations are in separate columns,
  format citations that were generated by get_all_citations as HTML, with 
  hyperlinks to every document that has a Bible citation.
  This uses the template file scripture-index-template.html.
  '''
  template = get_scripture_index_template()

  citation_html = replace_macro("PAGE_TITLE", 'Scripture Index', template)

  ot_books = old_testament_books()
  nt_books = new_testament_books()

  # <details class="scripture">
  #     <summary><h2>Book name</h2></summary>
  #     <p>This is the text that will show when you click on the summary text</p>
  # </details>
  old_testament_citations = ''
  new_testament_citations = ''
  for book in ot_books:
    if book in citations:
      old_testament_citations += citations_for_one_book(book, citations)

  for book in nt_books:
    if book in citations:
      new_testament_citations += citations_for_one_book(book, citations)

  citation_html = replace_macro("OLD_TESTAMENT_LINKS", old_testament_citations, citation_html)
  citation_html = replace_macro("NEW_TESTAMENT_LINKS", new_testament_citations, citation_html)
  return citation_html

def write_citations(citations: dict, filename: str):
  print(f'Write Scripture index to {filename}')
  # Single column, ignore template file, with both Old and New Testament together.
  # html = format_citations(citations)

  # Use template file, two columns, one for Old Testament, one for New Testament.
  html = format_citations_by_testament(citations)
  print(f'Size of index file: {len(html)}')
  with open(filename, 'w') as f:
    f.write(html)

###################

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

