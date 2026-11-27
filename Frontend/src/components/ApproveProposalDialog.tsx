import { useState } from "react";

export const MAX_DESCRIPTION_LENGTH = 200;

type ApproveProposalDialogProps = {
  customer: string;
  version: number;
  isSubmitting: boolean;
  onCancel: () => void;
  onConfirm: (description: string) => void;
};

/** Suggested description: only the first version gets a default text. */
function defaultApprovalDescription(customer: string, version: number): string {
  return version === 1 ? `Eerste versie voor ${customer}` : "";
}

export default function ApproveProposalDialog({
  customer,
  version,
  isSubmitting,
  onCancel,
  onConfirm,
}: Readonly<ApproveProposalDialogProps>) {
  const [description, setDescription] = useState(() => defaultApprovalDescription(customer, version));

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-anthracite/45">
      <dialog
        open
        aria-labelledby="approve-dialog-title"
        className="static flex flex-col gap-4 w-120 max-w-[calc(100vw-32px)] m-0 p-7 rounded-large bg-white"
      >
        <h2 id="approve-dialog-title" className="m-0 font-title text-xl font-bold">
          Proposal goedkeuren?
        </h2>

        <p className="m-0 text-sm text-grey">
          Na het goedkeuren controleert de AI het voorstel. Zolang die controle bezig is, kan het
          voorstel niet opnieuw goedgekeurd worden. De omschrijving kan achteraf niet meer aangepast worden.
        </p>

        <div className="flex flex-col gap-1.5">
          <label htmlFor="approve-description-input" className="text-xs font-semibold text-anthracite">
            Omschrijving
          </label>
          <textarea
            id="approve-description-input"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            maxLength={MAX_DESCRIPTION_LENGTH}
            placeholder="Bv. Leverdatum mapt nu op DeliveryDate in plaats van OrderDate (optioneel)"
            rows={3}
            disabled={isSubmitting}
            autoFocus
            className="px-3.5 py-2.5 border border-line-grey rounded-small text-sm outline-none resize-none focus:border-anthracite"
          />
          <div className="flex justify-end text-[11px]">
            <span className="text-grey tabular-nums">
              {description.length}/{MAX_DESCRIPTION_LENGTH}
            </span>
          </div>
        </div>

        <div className="flex justify-end gap-2.5">
          <button type="button" className="btn" onClick={onCancel} disabled={isSubmitting}>
            Annuleren
          </button>
          <button
            type="button"
            className="btn btn--primary flex items-center gap-2"
            onClick={() => onConfirm(description.trim())}
            disabled={isSubmitting}
          >
            {isSubmitting ? "AI-controle uitvoeren…" : "Bevestigen"}
          </button>
        </div>
      </dialog>
    </div>
  );
}