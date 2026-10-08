"""独立风险后台入口：python -m app.risk_worker；API 进程不运行计算任务。"""
import asyncio
import logging
import signal
import os
from app.core.config import get_settings
from app.db.sqlite import Base, get_engine
from app.db.risk_migrate import ensure_risk_schema
from app.db.migrate import ensure_sqlite_schema
from app.services.risk_engine import bootstrap, worker
from app.models import user, clue  # 注册已有模型，确保与 API 使用同一元数据。

logger = logging.getLogger('shenji.risk')


async def main():
    settings = get_settings()
    logger.info('风险后台启动 pid=%s，正在检查数据库结构', os.getpid())
    await ensure_risk_schema()
    async with get_engine().begin() as conn:
        await conn.exec_driver_sql('BEGIN IMMEDIATE')
        await conn.run_sync(Base.metadata.create_all)
    await ensure_sqlite_schema(get_engine())
    await bootstrap()
    logger.info('数据库初始化完成；模块=%s 计算=%s 定时调度=%s 源键已核实=%s；批量大小=%s',
                settings.RISK_MODULE_ENABLED, settings.RISK_RUN_ENABLED,
                settings.RISK_SCHEDULE_ENABLED, settings.RISK_SOURCE_KEY_VERIFIED, settings.RISK_BATCH_SIZE)
    logger.info('开始监听任务；Windows 按 Ctrl+C 停止后台')
    task=asyncio.create_task(worker())
    loop=asyncio.get_running_loop()
    try:
        loop.add_signal_handler(signal.SIGTERM,task.cancel)
    except NotImplementedError:
        pass  # Windows 本地运行使用 Ctrl+C，systemd 环境支持 SIGTERM。
    try:
        await task
    except asyncio.CancelledError:
        logger.info('收到停止信号，正在释放执行租约和数据库连接')
    finally:
        await get_engine().dispose()
        logger.info('风险后台已停止')


if __name__=='__main__':
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info('风险后台已由用户停止')
    except Exception:
        logger.exception('风险后台启动或退出失败')
        raise SystemExit(1)
