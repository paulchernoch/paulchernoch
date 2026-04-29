#!/bin/bash

# Build the website, add and commit changes to git with a user specified commit message, and push the changes to github.

# Prompt the user for input
echo "Commit message for git:"
read user_input

# Build the new index-2.html file from the template and markdown files.
# PUT CALL TO make-index-2.py HERE
python make-index-2.py --force Y

cd source


# Build the HTML files from the templates and markdown files.
python build-website.py force

cd ..

# Build the search index.
npx -y pagefind --site docs

git add .

git commit -m "$user_input"

git push

echo "Published!"
