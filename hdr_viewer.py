#!/usr/bin/env python3
"""HDR Viewer
Copyright: pigsboss@github
"""
import tkinter as tk
from PIL import Image, ImageTk
from os import path

root=tk.Tk()
fr_buttons=tk.Frame(root)
btn_open=tk.Button(fr_buttons, text='Open')
btn_save=tk.Button(fr_buttons, text='Save As...')
