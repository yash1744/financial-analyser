"use client";

/**
 * Receipt section for a transaction: editable details, an attachment
 * gallery (images or PDFs) with upload, and per-attachment / whole-receipt
 * deletion. All backend writes go through useReceiptMutations, which keeps
 * the receipt query cache in sync so the panel reflects each change
 * immediately.
 */

import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Spinner } from "@/components/ui/Spinner";
import { ApiError } from "@/lib/api/client";
import { api } from "@/lib/api/endpoints";
import type { Receipt, ReceiptDetailsUpdate } from "@/lib/api/types";
import { useReceipt, useReceiptMutations } from "@/lib/hooks";

const MAX_IMAGES = 10;
const ACCEPTED = "image/jpeg,image/png,image/webp,application/pdf";
const PDF_TYPE = "application/pdf";

type DetailForm = {
  merchant_name: string;
  receipt_date: string;
  notes: string;
  tax_amount: string;
  tip_amount: string;
  comments: string;
};

function toForm(receipt: Receipt | null): DetailForm {
  return {
    merchant_name: receipt?.merchant_name ?? "",
    receipt_date: receipt?.receipt_date ?? "",
    notes: receipt?.notes ?? "",
    tax_amount: receipt?.tax_amount ?? "",
    tip_amount: receipt?.tip_amount ?? "",
    comments: receipt?.comments ?? "",
  };
}

function toPayload(form: DetailForm): ReceiptDetailsUpdate {
  const trimmed = (v: string) => (v.trim() === "" ? null : v.trim());
  return {
    merchant_name: trimmed(form.merchant_name),
    receipt_date: trimmed(form.receipt_date),
    notes: trimmed(form.notes),
    tax_amount: trimmed(form.tax_amount),
    tip_amount: trimmed(form.tip_amount),
    comments: trimmed(form.comments),
  };
}

function errorText(error: unknown): string {
  if (error instanceof ApiError) return error.detail;
  if (error instanceof Error) return error.message;
  return "Something went wrong.";
}

const inputClass =
  "w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink placeholder:text-ink-3 focus:border-accent focus:outline-none";

export function ReceiptPanel({ transactionId }: { transactionId: string }) {
  const receiptQuery = useReceipt(transactionId);
  const { saveDetails, uploadImage, deleteImage, deleteReceipt } =
    useReceiptMutations(transactionId);
  const fileInput = useRef<HTMLInputElement>(null);

  const receipt = receiptQuery.data ?? null;
  const [form, setForm] = useState<DetailForm>(toForm(receipt));

  // sync the form when the receipt first loads / changes identity
  const receiptId = receipt?.id ?? null;
  const loadedRef = useRef<string | null>(null);
  useEffect(() => {
    if (loadedRef.current !== receiptId) {
      loadedRef.current = receiptId;
      setForm(toForm(receipt));
    }
  }, [receiptId, receipt]);

  if (receiptQuery.isPending) {
    return (
      <div className="flex justify-center py-6">
        <Spinner />
      </div>
    );
  }

  const images = receipt?.images ?? [];
  const atLimit = images.length >= MAX_IMAGES;

  const onPickFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) uploadImage.mutate(file);
    e.target.value = ""; // allow re-picking the same file
  };

  const set = (key: keyof DetailForm) => (v: string) =>
    setForm((f) => ({ ...f, [key]: v }));

  return (
    <div className="space-y-5">
      {/* Details */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <label className="flex flex-col gap-1">
          <span className="text-xs font-medium text-ink-2">Merchant</span>
          <input
            className={inputClass}
            value={form.merchant_name}
            onChange={(e) => set("merchant_name")(e.target.value)}
            placeholder="e.g. Corner Store"
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-xs font-medium text-ink-2">Receipt date</span>
          <input
            type="date"
            className={inputClass}
            value={form.receipt_date}
            onChange={(e) => set("receipt_date")(e.target.value)}
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-xs font-medium text-ink-2">Tax amount</span>
          <input
            type="number"
            step="0.01"
            min="0"
            className={inputClass}
            value={form.tax_amount}
            onChange={(e) => set("tax_amount")(e.target.value)}
            placeholder="0.00"
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-xs font-medium text-ink-2">Tip amount</span>
          <input
            type="number"
            step="0.01"
            min="0"
            className={inputClass}
            value={form.tip_amount}
            onChange={(e) => set("tip_amount")(e.target.value)}
            placeholder="0.00"
          />
        </label>
        <label className="flex flex-col gap-1 sm:col-span-2">
          <span className="text-xs font-medium text-ink-2">Notes</span>
          <textarea
            className={inputClass}
            rows={2}
            value={form.notes}
            onChange={(e) => set("notes")(e.target.value)}
            placeholder="What was this for?"
          />
        </label>
        <label className="flex flex-col gap-1 sm:col-span-2">
          <span className="text-xs font-medium text-ink-2">Comments</span>
          <textarea
            className={inputClass}
            rows={2}
            value={form.comments}
            onChange={(e) => set("comments")(e.target.value)}
          />
        </label>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <Button
          loading={saveDetails.isPending}
          onClick={() => saveDetails.mutate(toPayload(form))}
        >
          Save details
        </Button>
        {saveDetails.isSuccess && !saveDetails.isPending && (
          <span className="text-xs text-good">Saved.</span>
        )}
        {saveDetails.isError && (
          <span className="text-xs text-bad">
            {errorText(saveDetails.error)}
          </span>
        )}
      </div>

      {/* Attachments */}
      <div className="border-t border-line pt-4">
        <div className="mb-3 flex items-center justify-between">
          <h4 className="text-sm font-semibold text-ink">
            Attachments{" "}
            <span className="font-normal text-ink-3">
              ({images.length}/{MAX_IMAGES})
            </span>
          </h4>
          <input
            ref={fileInput}
            type="file"
            accept={ACCEPTED}
            className="hidden"
            onChange={onPickFile}
          />
          <Button
            variant="secondary"
            disabled={atLimit}
            loading={uploadImage.isPending}
            onClick={() => fileInput.current?.click()}
          >
            {atLimit ? "Limit reached" : "Upload file"}
          </Button>
        </div>

        {uploadImage.isError && (
          <p className="mb-3 text-xs text-bad">{errorText(uploadImage.error)}</p>
        )}

        {images.length === 0 ? (
          <p className="text-xs text-ink-3">
            No attachments yet. Upload JPEG, PNG, WebP, or PDF files (up to{" "}
            {MAX_IMAGES}).
          </p>
        ) : (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            {images.map((image) => {
              const isPdf = image.content_type === PDF_TYPE;
              const url = api.receiptImageUrl(transactionId, image.id);
              return (
                <figure
                  key={image.id}
                  className="group relative overflow-hidden rounded-lg border border-line"
                >
                  {isPdf ? (
                    <a
                      href={url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex h-32 w-full flex-col items-center justify-center gap-1 bg-line text-ink-3 hover:text-ink"
                      title={`Open ${image.file_name} in a new tab`}
                    >
                      <span className="rounded bg-bad/10 px-2 py-1 text-xs font-bold text-bad">
                        PDF
                      </span>
                      <span className="text-[11px]">Open in new tab</span>
                    </a>
                  ) : (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={url}
                      alt={image.file_name}
                      className="h-32 w-full object-cover"
                    />
                  )}
                  <div className="absolute right-1.5 top-1.5 flex gap-1 opacity-0 transition-opacity group-hover:opacity-100">
                    <a
                      href={url}
                      download={image.file_name}
                      className="rounded-md bg-black/60 px-2 py-1 text-xs text-white hover:bg-black/80"
                      aria-label={`Download ${image.file_name}`}
                    >
                      Download
                    </a>
                    <button
                      type="button"
                      onClick={() => deleteImage.mutate(image.id)}
                      className="rounded-md bg-black/60 px-2 py-1 text-xs text-white hover:bg-black/80"
                      aria-label={`Delete ${image.file_name}`}
                    >
                      Delete
                    </button>
                  </div>
                  <figcaption className="truncate px-2 py-1 text-[11px] text-ink-3">
                    {image.file_name}
                  </figcaption>
                </figure>
              );
            })}
          </div>
        )}
      </div>

      {receipt && (
        <div className="border-t border-line pt-4">
          <Button
            variant="ghost"
            className="text-bad"
            loading={deleteReceipt.isPending}
            onClick={() => deleteReceipt.mutate()}
          >
            Remove receipt
          </Button>
        </div>
      )}
    </div>
  );
}
