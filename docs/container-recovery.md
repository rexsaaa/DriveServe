# 固定容器环境与 OSS 恢复

该交付由2026-10-16用户要求新增，独立于v1.0.0历史性能验收。目标是在新Linux x86_64 GPU宿主上恢复固定用户态，不使用新机器预装的Python/PyTorch。

## 范围

镜像包含当前Ubuntu 22.04用户态的选定dpkg包文件、系统Python3.11.10、glibc2.35、GCC11.4、CUDA工具12.1.105、Compute Sanitizer、Nsight工具、固定GPU venv及训练/AWQ依赖层、三组vLLM overlay。固定提交的源码通过无凭据Git bundle内置；空工作目录首次启动时恢复该提交。

主环境为torch2.6.0+cu124/vLLM0.8.5/Transformers4.51.3，运行库包括CUDA12.4.127和cuDNN9.1.0.70。CUDA12.1是系统编译工具，12.4是PyTorch运行库。训练/AWQ层通过`DRIVESERVE_DEPENDENCY_LAYER=training`或`awq`显式启用，默认保持基础推理层。

模型、checkpoint和旧实验临时文件不塞入镜像；沿用既有OSS收据。镜像不包含/root、/home、SSH/OSS/Codex凭据、系统运行状态、宿主驱动或内核，也不打包全局预装pip环境。来源、每个文件的hash和系统包版本另存构建清单。

## 宿主要求

- Linux x86_64；可用的Docker及NVIDIA Container Toolkit，支持`docker run --gpus`。只提供一个受限PyTorch容器的平台，需要平台管理员提供GPU容器/自定义镜像入口。
- 驱动迁移基线`>=550.54.15`，原项目实测`550.163.01`；不是已测出的项目最低驱动。新显卡还须被当前torch/vLLM版本支持。
- 当前固定CUDA12.4镜像不支持Blackwell（例如RTX50系列）及更新架构，更新驱动不能解决全部问题，需要另建升级后的镜像并重新验证。RTX4090有项目实测；A100/H100等其他GPU仍须运行实际模型/算子检查，不能仅凭驱动版本判定兼容。
- 建议准备至少100GB可用存储，容纳镜像导入、恢复模型和下载/解包峰值。实际体积以镜像收据和所选模型为准。
- 本项目不修改宿主驱动、Docker守护进程或平台权限；不能通过关闭平台安全限制来启动镜像。

## 新机器恢复

### 使用平台“备份镜像导入”入口

本次OSS产物是标准Docker save格式的`.docker.tar.gz`，不是恒源云专用的整机备份。平台入口必须明确支持Docker/OCI容器镜像；如果只接受平台自己创建的快照，不能直接把该文件当作快照导入。此平台入口的格式兼容性尚未实测。可在支持Docker的宿主上先加载镜像，再推送到平台支持的私有镜像仓库；或者让平台按其文档从该容器建立平台快照。

平台需要提供GPU透传，并保留镜像入口`/opt/driveserve/entrypoint.sh`。初次启动命令为`python /opt/driveserve/check_runtime.py --gpu`；如平台覆盖ENTRYPOINT，应显式执行`/opt/driveserve/entrypoint.sh python /opt/driveserve/check_runtime.py --gpu`。启动工作目录为`/hy-netdisk/jq/project/DriveServe`。原机器预装PyTorch/CUDA版本可以不同，宿主驱动和GPU架构仍须满足上面的要求。

### 使用Docker宿主

在宿主机执行，先登录项目OSS账户；密码/令牌不要写入仓库。镜像内固定Python3.11，宿主恢复脚本需要Python3.11及平台`oss`命令。

```bash
git clone https://github.com/rexsaaa/DriveServe.git
cd DriveServe
oss login
python3 scripts/container_image.py restore --receipt reports/container-image-oss.json --directory /data/driveserve-image --load
python3 scripts/restore_container_models.py --directory /data/driveserve-assets --models target draft-distilled-v2 awq-domain-g128-v1
```

恢复脚本先检查归档SHA256及内部所有层/config的SHA256，再`docker load`，并检查导入后的image ID等于已固定config digest。不会覆盖不同内容的既有文件。镜像tag从收据读取：

```bash
image_tag=$(python3 -c 'import json; print(json.load(open("reports/container-image-oss.json"))["image"]["tag"])')
docker run --rm --gpus all --shm-size=8g \
  --mount type=bind,src="$PWD",dst=/hy-netdisk/jq/project/DriveServe \
  --mount type=bind,src=/data/driveserve-assets/models,dst=/hy-tmp/driveserve/models,readonly \
  "$image_tag" python /opt/driveserve/check_runtime.py --gpu
```

再进行实际模型生成：

```bash
docker run --rm --gpus '"device=0"' --shm-size=8g \
  --mount type=bind,src="$PWD",dst=/hy-netdisk/jq/project/DriveServe \
  --mount type=bind,src=/data/driveserve-assets/models,dst=/hy-tmp/driveserve/models,readonly \
  "$image_tag" python /opt/driveserve/check_runtime.py --gpu --model /hy-tmp/driveserve/models/target
```

没有GitHub访问时，可将一个空宿主目录挂载到项目工作目录，入口会从内置bundle恢复对应提交。不要将宿主整个`/hy-tmp/driveserve`覆盖挂载到镜像，会遮住固定venv与工具；只挂载模型和需要持久保存的输出目录。

检查通过后按`docs/reproduce.md`和冻结profile运行服务/实验。CUDA扩展在新机器重编译；正式测量仍需空闲GPU、干净Git和新run。容器环境固定不代表跨硬件性能相同。训练checkpoint/教师数据仍按原收据和训练恢复协议下载。

## 制作与验证

当前平台没有Docker守护进程、禁止用户命名空间。`scripts/container_image.py`从显式允许的本机包文件组装标准OCI层，不调用mount/unshare，不复制宿主驱动；再输出标准Docker save格式的gzip归档。可用共享内存暂存数据，不在noexec挂载上执行程序。

```bash
python3 scripts/container_image.py build --directory /dev/shm/driveserve-image-build
python3 scripts/container_image.py verify --directory /dev/shm/driveserve-image-build
python3 scripts/container_image.py archive --directory /dev/shm/driveserve-image-build --output /dev/shm/driveserve-image-build/driveserve.docker.tar.gz
python3 scripts/container_image.py backup --archive /dev/shm/driveserve-image-build/driveserve.docker.tar.gz --lock /dev/shm/driveserve-image-build/image-lock.json --prefix oss://DriveServe/container-images/UNIQUE-BUILD --receipt reports/container-image-oss.json
```

构建要求已提交且干净的源码；备份前缀每个镜像唯一，归档名称带hash。上传后重新完整下载，检查压缩包及每个未压缩层；仅删除本次生成的下载副本。镜像保存和完整GPU容器启动是不同验证项，最终实际证据见`reports/container-image-validation.json`；未实测项明确保留为未验证。
