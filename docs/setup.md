# Setting up Hacker Yardage for beginners

## Introduction

If you've never used Python before and/or don't even know what the command line is, this guide will help you get the Hacker Yardage tool set up. It should be doable for anyone, even a complete novice.

Please note that this guide is only meant to help you get set up with this particular tool. It will discuss a few basic concepts, but is not meant to be a comprehensive guide to Python or the command line interface.

## Setup

#### Step 1: Download and install Python

Assuming you don't have Python 3 already installed, you'll need to download it from the official Python website. Find the appropriate version for your operating system (i.e. Windows or Mac) and follow the instructions to install.

#### Step 2: Download the code to run the Hacker Yardage tool

Once you have Python installed, you'll also need to download the code for this tool. If you're a beginner, the easiest way will probably be to download a ZIP archive of all the project files directly from Github.

* Open up the home page for this project in a new window or tab.

/add link

* At the top right, click the "Code" button. In the dropdown, select "Download ZIP".

/add image

* Once it's downloaded, open the ZIP file. You should now have a folder called "hacker-yardage". You can move this folder wherever you want, but remember where you put it.


#### Step 3: Open up the command line

Next, we'll need to open the command line:

* For Windows users: click the Start button, type "cmd" in the search field, and hit Enter. This should open up cmd.exe, also called the Command Prompt. You should see something like this:

/add image

* For Mac users: open Spotlight, search for an app called "Terminal", and open it up. You should see something like this:

/add image


#### Some notes on the command line


**Note: you should be very careful when entering commands you find online in the command line. It's possible to harm your computer by running code you don't understand. Never copy and paste commands from the Internet into your command line and run them without knowing what they will do.**

#### Step 4: Navigate to the project folder from the command line

First, we need to move from the default folder the command line starts in to the hacker-yardage folder we just downloaded. To do that, we'll use the ```cd``` command. (```cd``` stands for 'change directory'.)

To get started, navigate to the hacker-yardage folder in either File Explorer (Windows) or Finder (Mac).

Next, we'll have to copy the path to the folder:

* On Windows: click the "Home" tab and then click the "Copy path" button.

* On Mac: simply copy the hacker-yardage folder itself. You can either do that by highlighting the folder pressing Command-C, or by right-clicking on the folder and selecting "Copy".

Finally, we are ready to run our ```cd``` command. Go back to your command line window and type in ```cd```, followed by a space. Then, paste the file path we just copied (Ctrl-V or Command-V).

Press Enter to execute the command. If you were successful, you should see the name of the current directory change to hacker-yardage:


If you see something else, try the above steps again. Make sure you are copying the path to the **folder** "hacker-yardage" itself, and not to one of the files or folders inside of it.


#### Step 5: Use ```pip``` to install some necessary packages

If you've successfully navigated to the project folder, you're almost there! We just need to get a little more code first, using a tool called ```pip```. (```pip``` stands for Pip Installs Packages, and it's kind of like an app store for Python code.)

The extra code we need to install is listed in ```requirements.txt```. So, to install this code, all we need to do is run the following command on the command line: ```pip install requirements.txt```

Type that into the command line and press enter. You should see a lot of information flow into the command line, detailing the download and install process.

(Note that this command will only work properly when we are in the project's home folder - that's why we had to navigate to it in the last step.)


#### Step 6: Run the Hacker Yardage tool

If you've successfully installed the extra packages using ```pip``` in the last step, you're ready to run the tool! Just type ```python3 hy-app.py``` into the command line, and a window should pop up.

(Note that this command will also only work properly when we are in the project's home folder. Every time you want to run the tool, you'll need to open the command line and navigate to the project folder as described in Step 4 above.)

#### You're done!

That's it! Hopefully you were able to
