#!/bin/bash

# Build the website, add and commit changes to git with a user specified commit message, and push the changes to github.

# Prompt the user for input
echo "Commit message for git:"
read user_input

cd source

python build-website.py force

cd ..

git add .

git commit -m "$user_input"

git push

echo "Published!"
