#!/bin/bash

# 获取当前日期时间戳
timestamp=$(date +"%Y%m%d%H%M")

# 检查传入的参数
if [ "$1" = "-make" ]; then
    # 创建data目录及其子目录
    mkdir -p data/images data/masks data/output
    echo "Directories data/images, data/masks, and data/output created."
elif [ "$1" = "-output" ]; then
    # 检查data目录是否存在
    if [ -d "data" ]; then
        # 重命名data目录并移动到指定路径
        mv data "test_$timestamp"
        mv "test_$timestamp" ~/autodl-tmp/
        echo "Directory data renamed to test_$timestamp and moved to ~/autodl-tmp/"
    else
        echo "Directory data does not exist."
    fi
elif [ "$1" = "-input" ]; then
    if [ -z "$2" ]; then
        echo "Please provide a directory name after -input."
    else
        src_dir=~/autodl-tmp/$2
        if [ -d "$src_dir/images" ] && [ -d "$src_dir/masks" ]; then
            mkdir -p data
            mv "$src_dir/images" data/
            mv "$src_dir/masks" data/
            echo "Directories images and masks moved from $src_dir to data/"
        else
            echo "Source directories $src_dir/images and/or $src_dir/masks do not exist."
        fi
    fi
elif [ "$1" = "-clean" ]; then
    # 删除data目录下的images、masks和output子目录中的所有文件
    if [ -d "data/images" ] && [ -d "data/masks" ] && [ -d "data/output" ]; then
        rm -rf data/images/*
        rm -rf data/masks/*
        rm -rf data/output/*
        echo "All files in data/images, data/masks, and data/output have been deleted."
    else
        echo "One or more directories (data/images, data/masks, data/output) do not exist."
    fi
else
    echo "Invalid option. Use -make to create directories, -output to rename and move the data directory, -input to move directories, or -clean to delete files in data subdirectories."
fi