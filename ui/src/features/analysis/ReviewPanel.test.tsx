import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { Finding } from "../../api/types";
import { ReviewPanel } from "./ReviewPanel";

const gap: Finding = {
  id: "ARCH-02:adr.md", rule_id: "ARCH-02", rule_title: "Reliable events", severity: "high", document: "adr.md",
  status: "gap", decided_by: "decider", confidence: 0.92, evidence: [{ section: "Publishing", text: "sends after commit" }],
  sections: [], reason: "", scope: "section", suggested_fix: "Use an outbox.", fix_source: "rule-hint",
};

describe("ReviewPanel", () => {
  it("approves with the edited fix and note", async () => {
    const onReview = vi.fn().mockResolvedValue(undefined);
    render(<ReviewPanel finding={gap} onReview={onReview} onUndo={vi.fn()} />);
    const fix = screen.getByRole("textbox", { name: /suggested fix/i });
    await userEvent.clear(fix);
    await userEvent.type(fix, "Write an outbox row in the same transaction.");
    await userEvent.type(screen.getByRole("textbox", { name: /note/i }), "agreed");
    await userEvent.click(screen.getByRole("button", { name: /approve: gap/i }));
    expect(onReview).toHaveBeenCalledWith({
      decision: "approved", verdict: undefined, note: "agreed", fix: "Write an outbox row in the same transaction.",
    });
  });

  it("drops the fix when the reviewer says the document is compliant", async () => {
    const onReview = vi.fn().mockResolvedValue(undefined);
    render(<ReviewPanel finding={gap} onReview={onReview} onUndo={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: /reject: compliant/i }));
    expect(onReview).toHaveBeenCalledWith(expect.objectContaining({ decision: "rejected", verdict: "compliant", fix: null }));
  });

  it("shows the saved decision with undo instead of the buttons", async () => {
    const onUndo = vi.fn().mockResolvedValue(undefined);
    render(
      <ReviewPanel finding={gap} onReview={vi.fn()} onUndo={onUndo}
        review={{ finding_id: gap.id, rule_id: "ARCH-02", document: "adr.md", decision: "approved", verdict: "gap",
          tool_status: "gap", note: "", fix: null, reviewed_at: "2026-10-18T10:00:00Z" }} />,
    );
    expect(screen.queryByRole("button", { name: /approve/i })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: /undo/i }));
    expect(onUndo).toHaveBeenCalled();
  });
});
