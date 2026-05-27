# BTP Debug Scripts

WSL bash 脚本，靠 mirrored networking 直连 Blender 的 127.0.0.1。

先 `chmod +x scripts/debug/*.sh` 一次。

## 命令速查

```bash
# 看现状
./list.sh                          # 只看名字列表
./status.sh                        # scene + 全 metadata + selection

# 改贴图（PUT 覆盖现有）
./put_stripes.sh                   # 默认改 T_test
./put_stripes.sh T_body
./put_checker.sh                   # 默认改 T_test
./put_checker.sh T_body

# 新建贴图（POST）
./post.sh T_new                    # 默认用 checker
./post.sh T_new stripes            # 指定用 stripes

# 改名
./rename.sh T_old T_new

# 验证字节 round-trip
./get_hash.sh T_test               # 跟 checker / stripes 的 hash 对比
```

## 测 undo / redo 的标准操作

```bash
# 场景: PUT undo + redo 测试
./put_stripes.sh T_test            # T_test 视觉上变红黄条
# 在 Blender 里 Ctrl-Z         → 应该看到 checker (粉灰格子)
# 在 Blender 里 Ctrl-Shift-Z   → 应该看到 stripes (回到红黄条)
./get_hash.sh T_test               # 拿 hash 对比 fixtures

# 场景: POST undo + redo 测试
./post.sh T_undo_test stripes      # 列表多了一张
./list.sh                          # 确认
# 在 Blender 里 Ctrl-Z         → 图消失
./list.sh                          # 确认
# 在 Blender 里 Ctrl-Shift-Z   → 图回来
./list.sh                          # 确认
```

## 环境变量

- `BTP_URL`: 默认 `http://127.0.0.1:18765`，端口改了可以 `export BTP_URL=http://127.0.0.1:NNNNN`。
