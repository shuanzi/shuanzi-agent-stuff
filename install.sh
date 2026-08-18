#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

CLAUDE_HOME="${CLAUDE_HOME:-$HOME/.claude}"
CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
AGENTS_HOME="${AGENTS_HOME:-$HOME/.agents}"

usage() {
  cat <<'USAGE'
用法：./install.sh

交互式安装本仓库的 hooks 和 skills：
  1. 自动识别当前环境已安装的 Agent（Claude Code / Codex），也可选通用 Agent 目录；
  2. 逐项勾选要安装的 hooks 和 skills；
  3. 可重复执行，同名内容以最后一次安装为准（覆盖旧版本）。

环境变量：
  CLAUDE_HOME   Claude Code 配置根目录（默认 ~/.claude）
  CODEX_HOME    Codex 配置根目录（默认 ~/.codex）
  AGENTS_HOME   通用 Agent 配置根目录（默认 ~/.agents）
USAGE
}

if [[ $# -gt 0 ]]; then
  if [[ $# -eq 1 && ( "$1" == "-h" || "$1" == "--help" ) ]]; then
    usage
    exit 0
  fi
  echo "install.sh 不接受命令行参数，请直接执行 ./install.sh。" >&2
  usage >&2
  exit 2
fi

cancel() {
  echo "安装已取消。" >&2
  exit 2
}

read_value() {
  local prompt="$1"
  local value
  if ! read -r -p "$prompt" value; then
    echo >&2
    cancel
  fi
  REPLY="$value"
}

read_yes_no() {
  local prompt="$1"
  local default="$2"
  local value

  while true; do
    read_value "$prompt"
    value="${REPLY:-$default}"
    case "$value" in
      y|Y) REPLY=true; return ;;
      n|N) REPLY=false; return ;;
      *) echo "请输入 y 或 n。" >&2 ;;
    esac
  done
}

command_exists() {
  command -v "$1" >/dev/null 2>&1
}

# ---------------------------------------------------------------------------
# 1. 选择 Agent
# ---------------------------------------------------------------------------

AGENT_IDS=()
AGENT_LABELS=()

claude_detected=false
if [[ -d "$CLAUDE_HOME" ]] || command_exists claude; then
  claude_detected=true
fi
codex_detected=false
if [[ -d "$CODEX_HOME" ]] || command_exists codex; then
  codex_detected=true
fi

if [[ "$claude_detected" == true ]]; then
  AGENT_IDS+=("claude")
  AGENT_LABELS+=("Claude Code（已检测到，skills 安装到 $CLAUDE_HOME/skills/）")
fi
if [[ "$codex_detected" == true ]]; then
  AGENT_IDS+=("codex")
  AGENT_LABELS+=("Codex（已检测到，skills 安装到 $CODEX_HOME/skills/）")
fi
AGENT_IDS+=("agents")
AGENT_LABELS+=("通用 Agent（skills 安装到 $AGENTS_HOME/skills/）")
if [[ "$claude_detected" == false ]]; then
  AGENT_IDS+=("claude")
  AGENT_LABELS+=("Claude Code（未检测到，仍会安装到 $CLAUDE_HOME/skills/）")
fi
if [[ "$codex_detected" == false ]]; then
  AGENT_IDS+=("codex")
  AGENT_LABELS+=("Codex（未检测到，仍会安装到 $CODEX_HOME/skills/）")
fi

echo "可用的 Agent："
for i in "${!AGENT_IDS[@]}"; do
  printf '  %d) %s\n' "$((i + 1))" "${AGENT_LABELS[$i]}"
done

while true; do
  read_value "请选择目标 Agent [1-${#AGENT_IDS[@]}]: "
  if [[ "$REPLY" =~ ^[0-9]+$ ]] && (( REPLY >= 1 && REPLY <= ${#AGENT_IDS[@]} )); then
    AGENT="${AGENT_IDS[$((REPLY - 1))]}"
    break
  fi
  echo "请输入 1 到 ${#AGENT_IDS[@]} 之间的编号。" >&2
done

case "$AGENT" in
  claude) SKILLS_TARGET="$CLAUDE_HOME/skills" ;;
  codex)  SKILLS_TARGET="$CODEX_HOME/skills" ;;
  *)      SKILLS_TARGET="$AGENTS_HOME/skills" ;;
esac

# ---------------------------------------------------------------------------
# 2. 选择安装内容
# ---------------------------------------------------------------------------

echo
echo "安装内容类型："
echo "  1) hooks"
echo "  2) skills"
echo "  3) 全部"

while true; do
  read_value "请选择内容类型 [1-3]: "
  case "$REPLY" in
    1) WANT_HOOKS=true;  WANT_SKILLS=false; break ;;
    2) WANT_HOOKS=false; WANT_SKILLS=true;  break ;;
    3) WANT_HOOKS=true;  WANT_SKILLS=true;  break ;;
    *) echo "请输入 1、2 或 3。" >&2 ;;
  esac
done

# 多选：输入编号（逗号分隔）、all 全选、q 放弃该类
# 用法：multi_select <提示> <结果数组名> <条目...>
multi_select() {
  local prompt="$1"
  local result_name="$2"
  shift 2
  local items=("$@")
  local count=${#items[@]}
  local selection=()

  if (( count == 0 )); then
    eval "$result_name=()"
    return
  fi

  echo
  echo "$prompt"
  for i in "${!items[@]}"; do
    printf '  %d) %s\n' "$((i + 1))" "${items[$i]}"
  done

  while true; do
    read_value "输入编号（逗号分隔，all 全选，q 放弃）: "
    case "$REPLY" in
      q|Q)
        selection=()
        break
        ;;
      all|ALL)
        selection=("${items[@]}")
        break
        ;;
      *)
        local valid=true
        selection=()
        IFS=',' read -r -a parts <<< "$REPLY"
        for part in "${parts[@]}"; do
          part="${part//[[:space:]]/}"
          if [[ "$part" =~ ^[0-9]+$ ]] && (( part >= 1 && part <= count )); then
            selection+=("${items[$((part - 1))]}")
          else
            valid=false
            break
          fi
        done
        if [[ "$valid" == true && ${#selection[@]} -gt 0 ]]; then
          break
        fi
        echo "输入无效，请输入 1 到 $count 之间的编号。" >&2
        ;;
    esac
  done

  eval "$result_name=(\"\${selection[@]}\")"
}

SELECTED_HOOKS=()
SELECTED_SKILLS=()

if [[ "$WANT_HOOKS" == true ]]; then
  HOOK_ITEMS=()
  while IFS= read -r dir; do
    HOOK_ITEMS+=("$(basename "$dir")")
  done < <(find "$REPO_DIR/hooks" -mindepth 1 -maxdepth 1 -type d | sort)
  multi_select "可安装的 hooks：" SELECTED_HOOKS "${HOOK_ITEMS[@]}"
fi

if [[ "$WANT_SKILLS" == true ]]; then
  SKILL_ITEMS=()
  while IFS= read -r dir; do
    SKILL_ITEMS+=("$(basename "$dir")")
  done < <(find "$REPO_DIR/skills" -mindepth 1 -maxdepth 1 -type d | sort)
  multi_select "可安装的 skills：" SELECTED_SKILLS "${SKILL_ITEMS[@]}"
fi

# 当前 hook 均为 Codex 专用
SKIPPED_HOOKS=()
if [[ ${#SELECTED_HOOKS[@]} -gt 0 && "$AGENT" != "codex" ]]; then
  echo
  echo "注意：当前 hooks 仅支持 Codex，目标 Agent 不是 Codex，将跳过 hooks 安装。" >&2
  SKIPPED_HOOKS=("${SELECTED_HOOKS[@]}")
  SELECTED_HOOKS=()
fi

if [[ ${#SELECTED_HOOKS[@]} -eq 0 && ${#SELECTED_SKILLS[@]} -eq 0 ]]; then
  echo "没有选中任何可安装的内容，安装结束。"
  exit 0
fi

# ---------------------------------------------------------------------------
# 3. 确认
# ---------------------------------------------------------------------------

echo
echo "安装汇总："
printf '  目标 Agent：  %s\n' "$AGENT"
printf '  skills 目录： %s\n' "$SKILLS_TARGET"
if [[ ${#SELECTED_HOOKS[@]} -gt 0 ]]; then
  printf '  hooks：       %s\n' "${SELECTED_HOOKS[*]}"
fi
if [[ ${#SELECTED_SKILLS[@]} -gt 0 ]]; then
  printf '  skills：      %s\n' "${SELECTED_SKILLS[*]}"
fi
if [[ ${#SKIPPED_HOOKS[@]} -gt 0 ]]; then
  printf '  跳过 hooks：  %s（仅支持 Codex）\n' "${SKIPPED_HOOKS[*]}"
fi
echo "同名已安装内容将被覆盖，以本次安装为准。"

read_yes_no "确认安装？[y/N]: " n
if [[ "$REPLY" != true ]]; then
  cancel
fi

# ---------------------------------------------------------------------------
# 4. 安装
# ---------------------------------------------------------------------------

OK_COUNT=0
FAIL_COUNT=0

# 拷贝 skill 目录（排除 .DS_Store），已存在则先删除实现覆盖
copy_skill() {
  local name="$1"
  local src="$REPO_DIR/skills/$name"
  local dest="$SKILLS_TARGET/$name"

  mkdir -p "$SKILLS_TARGET"
  rm -rf "$dest"
  cp -R "$src" "$dest"
  find "$dest" -name '.DS_Store' -delete
}

for skill in ${SELECTED_SKILLS[@]+"${SELECTED_SKILLS[@]}"}; do
  if copy_skill "$skill"; then
    printf '已安装 skill：%s -> %s\n' "$skill" "$SKILLS_TARGET/$skill"
    OK_COUNT=$((OK_COUNT + 1))
  else
    printf '安装 skill 失败：%s\n' "$skill" >&2
    FAIL_COUNT=$((FAIL_COUNT + 1))
  fi
done

for hook in ${SELECTED_HOOKS[@]+"${SELECTED_HOOKS[@]}"}; do
  hook_installer="$REPO_DIR/hooks/$hook/install.sh"
  if [[ ! -x "$hook_installer" ]]; then
    printf '找不到可执行的 hook 安装器：%s\n' "$hook_installer" >&2
    FAIL_COUNT=$((FAIL_COUNT + 1))
    continue
  fi
  echo
  echo "开始安装 hook：${hook}（将进入该 hook 自己的交互式配置）"
  if CODEX_HOME="$CODEX_HOME" "$hook_installer"; then
    OK_COUNT=$((OK_COUNT + 1))
  else
    printf '安装 hook 失败：%s\n' "$hook" >&2
    FAIL_COUNT=$((FAIL_COUNT + 1))
  fi
done

echo
printf '安装完成：成功 %d 项，失败 %d 项，跳过 %d 项。\n' \
  "$OK_COUNT" "$FAIL_COUNT" "${#SKIPPED_HOOKS[@]}"

if (( FAIL_COUNT > 0 )); then
  exit 1
fi
