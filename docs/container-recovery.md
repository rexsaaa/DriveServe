# 固定容器环境与 OSS 恢复

该交付由2026-10-16用户要求新增，独立于v1.0.0历史性能验收。目标是在新Linux x86_64 GPU宿主上恢复固定用户态，不使用新机器预装的Python/PyTorch。

## 范围

镜像包含当前Ubuntu 22.04用户态的选定dpkg包文件、系统Python3.11.10、glibc2.35、GCC11.4、CUDA工具12.1.105、Compute Sanitizer、Nsight工具、固定GPU venv及训练/AWQ依赖层、三组vLLM overlay。固定提交的源码通过无凭据Git bundle内置；空工作目录首次启动时恢复该提交。

主环境为torch2.6.0+cu124/vLLM0.8.5/Transformers4.51.3，运行库包括CUDA12.4.127和cuDNN9.1.0.70。CUDA12.1是系统编译工具，12.4是PyTorch运行库。训练/AWQ层通过`DRIVESERVE_DEPENDENCY_LAYER=training`或`awq`显式启用，默认保持基础推理层。

模型、checkpoint和旧实验临时文件不塞入镜像；沿用既有OSS收据。镜像不包含/root、/home、SSH/OSS/Codex凭据、系统运行状态、宿主驱动或内核，也不打包全局预装pip环境。来源、每个文件的hash和系统包版本另存构建清单。

当前镜像tag：`driveserve:portable-eb7cdf5ccb06`；内置源码提交`eb7cdf5ccb06465ed7f7952f6f20405524caf786`。Docker归档10,232,606,095bytes（约10.23GB），SHA256为`d75fe7bbf0976fe94697a2f756d2be3f05689d9d8cb4ae1b9ea3d04c061b8001`。镜像和配套恢复包保存在`oss://DriveServe/container-images/20261016-eb7cdf5ccb06/`，明细见[镜像收据](../reports/container-image-oss.json)和[恢复包收据](../reports/container-recovery-kit-oss.json)。历史v1.0.0标签不移动。

## 宿主要求

- Linux x86_64；可用的Docker及NVIDIA Container Toolkit，支持`docker run --gpus`。只提供一个受限PyTorch容器的平台，需要平台管理员提供GPU容器/自定义镜像入口。
- 驱动迁移基线`>=550.54.15`，原项目实测`550.163.01`；不是已测出的项目最低驱动。新显卡还须被当前torch/vLLM版本支持。
- 当前固定CUDA12.4镜像不支持Blackwell（例如RTX50系列）及更新架构，更新驱动不能解决全部问题，需要另建升级后的镜像并重新验证。RTX4090有项目实测；A100/H100等其他GPU仍须运行实际模型/算子检查，不能仅凭驱动版本判定兼容。
- 建议准备至少100GB可用存储，容纳镜像导入、恢复模型和下载/解包峰值。实际体积以镜像收据和所选模型为准。
- 本项目不修改宿主驱动、Docker守护进程或平台权限；不能通过关闭平台安全限制来启动镜像。

## 新机器恢复

### 原项目目录和GitHub都不可用时

在已登录项目OSS的Linux机器执行下列命令。恢复包内有无凭据Git bundle、镜像收据、模型收据和恢复说明，不依赖原机器的任何目录；宿主需要Git、tar、Python3.11和平台OSS客户端。

```bash
mkdir driveserve-recovery
cd driveserve-recovery
oss cp oss://DriveServe/container-images/20261016-eb7cdf5ccb06/recovery-kit.tar.gz ./recovery-kit.tar.gz -p=2
oss cp oss://DriveServe/container-images/20261016-eb7cdf5ccb06/recovery-index.tar.gz ./recovery-index.tar.gz -p=2
tar -xzf recovery-index.tar.gz
sha256sum --ignore-missing -c SHA256SUMS
tar -xzf recovery-kit.tar.gz
git clone source.bundle DriveServe
cp -a recovery-files/. DriveServe/
cd DriveServe
```

随后按下方Docker命令从`oss login`之后继续。恢复包补充了镜像制作完成后的收据/文档，工作区会出现这些有意新增的材料；正式测量前按项目证据规范固定自己的提交。该恢复包本身的上传收据由GitHub保存，包内不包含自身的最终hash收据。

### 使用平台“备份镜像导入”入口

本次OSS产物是标准Docker save格式的`.docker.tar.gz`。[恒源云官方镜像文档](https://gpushare.com/docs/instance/image/#import-image)（2026-10-16查阅）明确支持`docker save`后gzip压缩、上传个人数据，再进入“实例与数据 → 我的镜像 → OSS导入”。选择该目录下`driveserve-d75fe7bbf0976fe9.docker.tar.gz`，不要选择配套恢复包。官方文档称DockerHub导入已取消。

**平台发行版限制尚未消除：**该官方文档只列Ubuntu18.04/20.04，本镜像固定的是当前项目Ubuntu22.04用户态。平台可能拒绝，尚未执行实际导入；不能保证当前控制台已支持22.04。导入时平台还会安装工具，完成后须重新运行环境检查。若不接受22.04，需要平台确认支持或使用标准Docker GPU宿主；不要为了绕过检查伪改发行版标识，也不要把更改基础发行版当作同一个已固定环境。

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

同一固定运行环境更新源码时，可加`build --reuse-runtime <已验证构建目录>`复用前三层；这不会采集宿主中新安装的依赖。环境有变化时应完整重建。导出可用`archive --pigz /path/to/pigz`并行压缩。

本次验证包括43项测试全通过、skopeo独立读取OCI和Docker归档且配置一致、umoci独立解包后的61,495普通文件hash和6,385软链接核对、3,331个venv/addon链接的镜像内目标解析。仅从镜像取出的系统用户态在隔离根目录中成功运行Python/SSL/SQLite/ctypes、nvcc并编译sm_89 PTX，入口能恢复空源码目录。现有宿主两张4090通过实际torch矩阵运算；Draft模型8文件从OSS重新恢复并逐一核验。

上述隔离用户态检查未执行完整venv的torch/vLLM容器运行；本机没有Docker守护进程，因此`docker load`、GPU容器透传启动、平台控制台导入和新机器模型生成仍须在目标机器验证。仅当目标机器环境检查和实际模型生成均通过，才算完成该机器的运行恢复。
