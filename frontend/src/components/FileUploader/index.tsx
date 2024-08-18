import React from 'react';
import Box from '@cloudscape-design/components/box';
import Button from '@cloudscape-design/components/button';
import FormField from '@cloudscape-design/components/form-field';

import { FileEntry } from './FileEntry';
import { Token } from './Token';

export interface IProp {
    fileInputId: string;
    text: string;
    label?: string;
    description?: string;
    info?: React.ReactNode;
    constraintText?: string;
    errorText?: string;
    files: File[];
    accept?: string;
    onFilesUploaded: (uploadedFiles: File[]) => void;
    onFileRemoved?: (fileIdx: number) => void;
    multiple?: boolean;
    i18nStrings?: {
        numberOfBytes: (n: number) => string;
        lastModified: (d: Date) => string;
    };
}

export const FileUploader = ({
    fileInputId,
    text,
    label,
    description,
    info,
    constraintText,
    errorText,
    files,
    onFilesUploaded,
    onFileRemoved,
    multiple = false,
    i18nStrings,
    accept,
}: IProp) => {
    return (
        <>
            <FormField
                info={info}
                label={label}
                description={description}
                constraintText={constraintText}
                errorText={errorText}
            >
                <Button
                    formAction="none"
                    iconName="upload"
                    onClick={() => {
                        document.getElementById(fileInputId)?.click();
                    }}
                >
                    <input
                        id={fileInputId}
                        type="file"
                        multiple={multiple}
                        hidden
                        accept={accept}
                        onChange={() => {
                            const fileInput = document.getElementById(fileInputId);

                            if (fileInput) onFilesUploaded(Array.from((fileInput as HTMLInputElement).files));
                        }}
                    />
                    {text}
                </Button>
            </FormField>
            <Box margin={{ top: 'xs' }}>
                {files &&
                    files.length > 0 &&
                    (multiple ? (
                        Array.from(files).map((file, fileIdx) => (
                            <div key={`file-${fileIdx}`} data-testid={`token-${file.name}`}>
                                <Token
                                    onClose={
                                        onFileRemoved
                                            ? () => {
                                                  onFileRemoved(fileIdx);
                                              }
                                            : undefined
                                    }
                                >
                                    <FileEntry file={file} showImage i18nStrings={i18nStrings} />
                                </Token>
                            </div>
                        ))
                    ) : (
                        <FileEntry file={files[0]} i18nStrings={i18nStrings} />
                    ))}
            </Box>
        </>
    );
};
