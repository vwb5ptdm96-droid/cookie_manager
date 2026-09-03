"""
repair_service_extension.py
扩展已有的 repair_service，增加对 ScriptRun 失败时的自动报单与 Agent 派单能力
"""
import logging
from typing import Optional, Any
from sqlalchemy.orm import Session
from app.services.agent_repair_dispatcher import agent_repair_dispatcher

logger = logging.getLogger(__name__)

class RepairServiceAutoExtension:
    """
    负责处理由自动化运行失败触发的工单与 Agent 派发
    """
    @staticmethod
    def handle_script_failure(
        db: Session,
        script_run_id: int,
        script_path: str,
        channel: str,
        shop_name: str,
        cdp_port: int,
        error_message: str,
        auto_dispatch_agent: bool = True
    ) -> Optional[Any]:
        from app.models.repair_ticket import RepairTicket

        logger.warning(
            f"[AutoRepair] 检测到脚本运行失败 (Run #{script_run_id}): "
            f"channel={channel}, shop={shop_name}, port={cdp_port}"
        )

        try:
            existing_ticket = db.query(RepairTicket).filter(
                RepairTicket.channel == channel,
                RepairTicket.shop_name == shop_name,
                RepairTicket.status.in_(["PENDING", "PROCESSING", "IN_PROGRESS"])
            ).first()

            if existing_ticket:
                ticket = existing_ticket
                ticket.description = f"[重试失败] {error_message[:500]}"
                logger.info(f"[AutoRepair] 复用已有未解决工单 Ticket #{ticket.id}")
            else:
                ticket = RepairTicket(
                    channel=channel,
                    shop_name=shop_name,
                    cdp_port=cdp_port,
                    issue_type="SCRIPT_FAILURE",
                    description=f"脚本自动执行失败: {error_message[:500]}",
                    status="PENDING"
                )
                db.add(ticket)
                db.commit()
                db.refresh(ticket)
                logger.info(f"[AutoRepair] 创建新维修工单 Ticket #{ticket.id}")

            if auto_dispatch_agent:
                agent_repair_dispatcher.trigger_claude_repair(
                    ticket_id=ticket.id,
                    channel=channel,
                    shop_name=shop_name,
                    cdp_port=cdp_port,
                    script_path=script_path,
                    issue_type="SCRIPT_FAILURE"
                )

            return ticket

        except Exception as e:
            logger.error(f"[AutoRepair] 自动建单或派发 Agent 失败: {e}", exc_info=True)
            db.rollback()
            return None
