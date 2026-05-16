# Docker 运行产物目录

此目录用于存放 Docker 构建和运行过程中生成的文件。

## 📁 目录结构

```
docker/
├── images/          # Docker 镜像导出文件（.tar/.tar.gz）
├── backups/         # 数据库备份文件（.sql/.sql.gz）
├── logs/            # 应用日志文件
└── README.md        # 本说明文件
```

## 📝 说明

- **images/**: 使用 `docker save` 导出的镜像文件
- **backups/**: PostgreSQL 数据库备份文件
- **logs/**: Flask 应用运行时产生的日志（需配置卷挂载）

## ⚠️ 注意

此目录下的文件通常较大，已添加到 `.gitignore`，不会被提交到 Git 仓库。
