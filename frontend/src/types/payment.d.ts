declare interface IPayment {
    id: string,
    type: "invoice" | "manual",
    created_at: string,
    value: number,
    description: string
}
