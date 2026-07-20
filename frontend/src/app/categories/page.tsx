"use client";

import { useState } from "react";

import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Field, Select, TextInput } from "@/components/ui/Field";
import { SkeletonLines } from "@/components/ui/Skeleton";
import { ApiError } from "@/lib/api/client";
import {
  useCategories,
  useCategoryMappingMutations,
  useCategoryMappings,
  useUserCategories,
  useUserCategoryManagement,
} from "@/lib/hooks";

const UNASSIGNED = "";

function errorText(error: unknown): string {
  if (error instanceof ApiError) return error.detail;
  if (error instanceof Error) return error.message;
  return "Something went wrong.";
}

function CreateCategoryForm() {
  const [name, setName] = useState("");
  const { createUserCategory } = useUserCategoryManagement();

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    createUserCategory.mutate(name.trim(), { onSuccess: () => setName("") });
  };

  return (
    <form onSubmit={submit} className="flex flex-wrap items-end gap-3">
      <Field label="New category">
        <TextInput
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="e.g. Dining Out"
          maxLength={100}
        />
      </Field>
      <Button type="submit" loading={createUserCategory.isPending}>
        Create
      </Button>
      {createUserCategory.isError && (
        <p className="text-xs text-bad">{errorText(createUserCategory.error)}</p>
      )}
    </form>
  );
}

function UserCategoryRow({
  category,
}: {
  category: { id: string; name: string };
}) {
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(category.name);
  const { renameUserCategory, deleteUserCategory } = useUserCategoryManagement();

  if (editing) {
    return (
      <div className="flex items-center gap-2 py-2">
        <TextInput
          autoFocus
          value={name}
          maxLength={100}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Escape") setEditing(false);
          }}
          className="max-w-xs"
        />
        <Button
          className="px-3 py-1 text-xs"
          loading={renameUserCategory.isPending}
          onClick={() =>
            renameUserCategory.mutate(
              { categoryId: category.id, name },
              { onSuccess: () => setEditing(false) },
            )
          }
        >
          Save
        </Button>
        <Button variant="ghost" className="px-3 py-1 text-xs" onClick={() => setEditing(false)}>
          Cancel
        </Button>
      </div>
    );
  }

  return (
    <div className="flex items-center justify-between border-b border-line py-2 last:border-b-0">
      <span className="text-sm text-ink">{category.name}</span>
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={() => {
            setName(category.name);
            setEditing(true);
          }}
          className="text-xs text-ink-3 underline-offset-2 hover:text-accent hover:underline"
        >
          Rename
        </button>
        <button
          type="button"
          onClick={() => deleteUserCategory.mutate(category.id)}
          className="text-xs text-bad underline-offset-2 hover:underline"
        >
          Delete
        </button>
      </div>
    </div>
  );
}

function MappingRow({
  plaidCategory,
  userCategories,
  currentUserCategoryId,
}: {
  plaidCategory: { id: string; name: string };
  userCategories: { id: string; name: string }[];
  currentUserCategoryId: string | undefined;
}) {
  const { setMapping, removeMapping } = useCategoryMappingMutations();

  const onChange = (value: string) => {
    if (value === UNASSIGNED) {
      removeMapping.mutate(plaidCategory.id);
    } else {
      setMapping.mutate({ categoryId: plaidCategory.id, userCategoryId: value });
    }
  };

  return (
    <div className="flex items-center justify-between gap-3 border-b border-line py-2 last:border-b-0">
      <span className="truncate text-sm text-ink">{plaidCategory.name}</span>
      <Select
        value={currentUserCategoryId ?? UNASSIGNED}
        onChange={(e) => onChange(e.target.value)}
        className="max-w-[12rem]"
      >
        <option value={UNASSIGNED}>Unassigned</option>
        {userCategories.map((uc) => (
          <option key={uc.id} value={uc.id}>
            {uc.name}
          </option>
        ))}
      </Select>
    </div>
  );
}

export default function CategoriesPage() {
  const userCategories = useUserCategories();
  const plaidCategories = useCategories();
  const mappings = useCategoryMappings();

  const mappingByCategoryId = new Map(
    (mappings.data ?? []).map((m) => [m.category_id, m.user_category_id]),
  );
  const myCategories = userCategories.data ?? [];

  return (
    <>
      <PageHeader
        title="Categories"
        subtitle="Group Plaid's categories into your own, for custom analytics"
      />

      <Card className="mb-4">
        <h3 className="mb-3 text-sm font-semibold text-ink">My categories</h3>
        {userCategories.isPending ? (
          <SkeletonLines lines={3} />
        ) : userCategories.isError ? (
          <ErrorState error={userCategories.error} onRetry={() => userCategories.refetch()} />
        ) : myCategories.length === 0 ? (
          <p className="mb-3 text-sm text-ink-3">
            You haven&apos;t created any categories yet.
          </p>
        ) : (
          <div className="mb-4">
            {myCategories.map((c) => (
              <UserCategoryRow key={c.id} category={c} />
            ))}
          </div>
        )}
        <CreateCategoryForm />
      </Card>

      <Card>
        <h3 className="mb-1 text-sm font-semibold text-ink">Assign Plaid categories</h3>
        <p className="mb-3 text-xs text-ink-3">
          Every category below comes from Plaid. Assign one or more to a category of
          your own to roll their spending up together in Analytics.
        </p>
        {plaidCategories.isPending || userCategories.isPending || mappings.isPending ? (
          <SkeletonLines lines={6} />
        ) : plaidCategories.isError ? (
          <ErrorState error={plaidCategories.error} onRetry={() => plaidCategories.refetch()} />
        ) : plaidCategories.data.length === 0 ? (
          <EmptyState
            title="No categories yet"
            hint="Categories appear automatically once transactions sync."
          />
        ) : myCategories.length === 0 ? (
          <p className="text-sm text-ink-3">
            Create a category above before assigning Plaid categories to it.
          </p>
        ) : (
          <div>
            {plaidCategories.data.map((c) => (
              <MappingRow
                key={c.id}
                plaidCategory={c}
                userCategories={myCategories}
                currentUserCategoryId={mappingByCategoryId.get(c.id)}
              />
            ))}
          </div>
        )}
      </Card>
    </>
  );
}
