"""Reuse Java test dependencies and real WorldMcpTools without HTTP or production DB."""
import json
import os
from pathlib import Path
import queue
import subprocess
import threading
import xml.etree.ElementTree as ET

from tools.remote_world import RemoteWorld

ROOT = Path(__file__).resolve().parents[1]


class JavaBridge:
    def __init__(self, directory: Path):
        reports = sorted((ROOT / "world-service/target/surefire-reports").glob("TEST-*.xml"))
        if not reports:
            raise RuntimeError("先运行 mvn -f world-service/pom.xml test，生成 Eval 所需的 Java 测试 classpath。")
        properties = ET.parse(reports[0]).getroot().find("properties")
        classpath = next(p.attrib["value"] for p in properties if p.attrib["name"] == "java.class.path")
        self.directory = directory
        # Windows Java 17 按本机代码页读 @argfile，UTF-8 会损坏含 Unicode 的 Maven 路径。
        # 使用原生 argv 传递路径；不依赖 JVM 对参数文件的编码解释。
        self.arguments = ["-Dfile.encoding=UTF-8", "-cp", classpath,
                          "org.novelworld.world.StructuralEvalBridge",
                          "jdbc:h2:file:" + (directory / "world").as_posix() + ";DB_CLOSE_DELAY=-1"]
        self.process = None
        try:
            self.start()
        except Exception:
            self.close()
            raise

    def start(self):
        java = str(Path(os.environ["JAVA_HOME"]) / "bin/java") if os.environ.get("JAVA_HOME") else "java"
        self.log = (self.directory / "java.stderr.log").open("a", encoding="utf-8")
        self.process = subprocess.Popen([java, *self.arguments], stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=self.log, text=True, encoding="utf-8")
        self.lines = queue.Queue()
        process, lines = self.process, self.lines
        def read_lines():
            for line in process.stdout:
                lines.put(line.rstrip("\r\n"))
            lines.put(None)
        threading.Thread(target=read_lines, daemon=True).start()
        if self.read() != "READY":
            raise RuntimeError("Java Eval bridge 启动失败；重新运行 Java tests 编译入口。")

    def read(self):
        try:
            value = self.lines.get(timeout=30)
        except queue.Empty as error:
            raise RuntimeError("Java Eval 超过 30 秒无响应") from error
        if value is None:
            raise RuntimeError("Java Eval 进程已退出；查看临时 java.stderr.log")
        return value

    def call(self, name, arguments):
        self.process.stdin.write(json.dumps({"name": name, "arguments": arguments}, ensure_ascii=False) + "\n")
        self.process.stdin.flush()
        result = json.loads(self.read())
        if "error" in result:
            raise ValueError(result["error"])
        return result["output"]

    def close(self):
        if self.process is not None:
            self.process.stdin.close()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
            self.process.stdout.close()
            self.log.close()
            self.process = None

    def restart(self):
        self.close()
        self.start()


class EvalWorld(RemoteWorld):
    def __init__(self, world_id, bridge):
        super().__init__(world_id)
        self.bridge = bridge

    def _call(self, name, arguments):
        return self.bridge.call(name, arguments)
